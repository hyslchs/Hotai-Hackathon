from __future__ import annotations

import hashlib
import json
import pickle
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import hdbscan
import numpy as np

from pipeline.clustering.experiments import (
    fit_candidate,
    load_coordinate_pool,
    sha256_file,
)
from pipeline.clustering.geometry import (
    deterministic_stratified_sample,
    haversine_km,
    points_digest,
    region_for_point,
)

TAIPEI_AREA_ARTIFACT_VERSION = "phase3-taipei-area-v1"
FALLBACK_AREA_BY_REGION = {
    "Taipei": "fallback_taipei",
    "Taichung": "fallback_taichung",
    "Kaohsiung": "fallback_kaohsiung",
    "Other/Unknown": "fallback_other_unknown",
}


@dataclass(frozen=True)
class AreaConfig:
    policy: str = "eligible_only"
    fit_split: str = "train"
    sample_size: int = 200_000
    min_cluster_size: int = 250
    min_samples: int = 25
    cluster_selection_method: str = "eom"
    seed: int = 20260918
    batch_size: int = 50_000


@dataclass(frozen=True)
class PointAssignment:
    area_id: str
    source: str
    region: str


def _json_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def area_id_for_cluster(label: int) -> str:
    return f"taipei_area_{int(label):04d}"


def fallback_area_id(region: str) -> str:
    return FALLBACK_AREA_BY_REGION.get(
        region,
        FALLBACK_AREA_BY_REGION["Other/Unknown"],
    )


def _cluster_radius(points: Sequence[tuple[float, float, str]]) -> float:
    if not points:
        return 0.0
    center_lat = sum(point[0] for point in points) / len(points)
    center_lng = sum(point[1] for point in points) / len(points)
    distances = [
        haversine_km(point[0], point[1], center_lat, center_lng)
        for point in points
    ]
    return float(np.quantile(np.asarray(distances, dtype=np.float64), 0.90))


def _expected_contract(input_path: Path, config: AreaConfig) -> dict[str, Any]:
    return {
        "artifact_version": TAIPEI_AREA_ARTIFACT_VERSION,
        "input_sha256": sha256_file(input_path),
        "config": json.loads(json.dumps(asdict(config))),
        "scope": "Taipei Demo only",
        "fallback_policy": "noise_or_non_taipei_to_region_fallback",
    }


def _existing_matches(
    metadata_path: Path,
    model_path: Path,
    expected: dict[str, Any],
) -> bool:
    if not metadata_path.exists() or not model_path.exists():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return all(metadata.get(key) == value for key, value in expected.items())


def fit_taipei_area_model(
    input_path: Path,
    output_dir: Path,
    config: AreaConfig | None = None,
) -> dict[str, Any]:
    config = config or AreaConfig()
    input_path = input_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "area_artifact.json"
    model_path = output_dir / "area_model.pkl"
    report_path = output_dir / "area_artifact.md"
    expected = _expected_contract(input_path, config)

    if _existing_matches(metadata_path, model_path, expected):
        return load_area_artifact(output_dir)

    include_soft_outliers = config.policy != "eligible_only"
    pool = load_coordinate_pool(
        input_path,
        include_soft_outliers=include_soft_outliers,
        split=config.fit_split,
        batch_size=config.batch_size,
    )
    if config.sample_size > len(pool):
        raise ValueError(
            f"area sample size {config.sample_size} exceeds coordinate pool {len(pool)}"
        )
    sample = deterministic_stratified_sample(pool, config.sample_size)
    model, labels, metrics = fit_candidate(
        sample,
        min_cluster_size=config.min_cluster_size,
        min_samples=config.min_samples,
        cluster_selection_method=config.cluster_selection_method,
    )

    cluster_points: dict[int, list[tuple[float, float, str]]] = {}
    for point, label in zip(sample, labels.tolist()):
        if int(label) >= 0:
            cluster_points.setdefault(int(label), []).append(point)

    cluster_to_area: dict[str, str] = {}
    areas: list[dict[str, Any]] = []
    for label in sorted(cluster_points):
        members = cluster_points[label]
        region_counts = Counter(point[2] for point in members)
        dominant_region, dominant_count = sorted(
            region_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]
        if dominant_region != "Taipei":
            continue
        area_id = area_id_for_cluster(label)
        cluster_to_area[str(label)] = area_id
        center_lat = sum(point[0] for point in members) / len(members)
        center_lng = sum(point[1] for point in members) / len(members)
        areas.append(
            {
                "area_id": area_id,
                "cluster_label": label,
                "sample_point_count": len(members),
                "dominant_region": dominant_region,
                "dominant_region_share": dominant_count / len(members),
                "centroid": {
                    "latitude": round(center_lat, 8),
                    "longitude": round(center_lng, 8),
                },
                "equivalent_radius_km_p90": round(_cluster_radius(members), 6),
            }
        )

    sample_digest = points_digest(sample)
    model_version = (
        f"taipei-area-v1-{expected['input_sha256'][:12]}-"
        f"{sample_digest[:12]}-{config.min_cluster_size}-"
        f"{config.min_samples}-{config.cluster_selection_method}"
    )
    metadata = {
        **expected,
        "model_version": model_version,
        "pool_point_count": len(pool),
        "sample_point_count": len(sample),
        "sample_digest": sample_digest,
        "fit_metrics": {
            key: value
            for key, value in metrics.items()
            if key not in {"fit_seconds", "peak_rss_mb"}
        },
        "cluster_to_area": cluster_to_area,
        "areas": areas,
        "supported_regions": ["Taipei"],
        "fallback_area_by_region": FALLBACK_AREA_BY_REGION,
        "artifact_hash": None,
    }
    metadata["artifact_hash"] = _json_digest(
        {
            key: value
            for key, value in metadata.items()
            if key != "artifact_hash"
        }
    )

    model_path.write_bytes(pickle.dumps(model, protocol=4))
    _write_json(metadata_path, metadata)
    report_path.write_text(
        "\n".join(
            [
                "# Taipei Demo area artifact",
                "",
                "此 artifact 只服務 Taipei Demo，不代表全台 production area model。",
                "",
                f"- model_version: {model_version}",
                f"- input_sha256: {expected['input_sha256']}",
                f"- fit_split: {config.fit_split}",
                f"- policy: {config.policy}",
                f"- sample: {config.sample_size} deterministic points",
                f"- HDBSCAN: {config.min_cluster_size}/{config.min_samples}/{config.cluster_selection_method}",
                f"- verified Taipei areas: {len(areas)}",
                f"- fallback: {expected['fallback_policy']}",
                f"- artifact_hash: {metadata['artifact_hash']}",
                "",
                "Noise、非 Taipei cluster 與不支援區域不會被稱為 verified area；它們會使用明確的 region fallback bucket。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "metadata": metadata,
        "model": model,
        "paths": {
            "metadata": metadata_path,
            "model": model_path,
            "report": report_path,
        },
    }


def load_area_artifact(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    metadata_path = output_dir / "area_artifact.json"
    model_path = output_dir / "area_model.pkl"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with model_path.open("rb") as handle:
        model = pickle.load(handle)
    return {
        "metadata": metadata,
        "model": model,
        "paths": {
            "metadata": metadata_path,
            "model": model_path,
            "report": output_dir / "area_artifact.md",
        },
    }


def assign_points(
    model: Any,
    points: Sequence[tuple[float, float]],
    cluster_to_area: dict[str, str],
) -> list[PointAssignment]:
    if not points:
        return []
    coordinates = np.radians(np.asarray(points, dtype=np.float64))
    labels, _strengths = hdbscan.approximate_predict(model, coordinates)
    assignments: list[PointAssignment] = []
    for point, label in zip(points, np.asarray(labels, dtype=np.int64).tolist()):
        region = region_for_point(point[0], point[1])
        area_id = cluster_to_area.get(str(int(label)))
        if area_id is not None and region == "Taipei":
            assignments.append(PointAssignment(area_id, "model", region))
        else:
            assignments.append(
                PointAssignment(
                    fallback_area_id(region),
                    "fallback",
                    region,
                )
            )
    return assignments


def assign_rows(
    model: Any,
    pickup_points: Sequence[tuple[float, float]],
    dropoff_points: Sequence[tuple[float, float]],
    cluster_to_area: dict[str, str],
) -> tuple[list[PointAssignment], list[PointAssignment]]:
    if len(pickup_points) != len(dropoff_points):
        raise ValueError("pickup and dropoff point counts must match")
    points = list(pickup_points) + list(dropoff_points)
    assignments = assign_points(model, points, cluster_to_area)
    size = len(pickup_points)
    return assignments[:size], assignments[size:]


def artifact_contract(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_version": metadata["artifact_version"],
        "model_version": metadata["model_version"],
        "input_sha256": metadata["input_sha256"],
        "fit_split": metadata["config"]["fit_split"],
        "policy": metadata["config"]["policy"],
        "sample_point_count": metadata["sample_point_count"],
        "sample_digest": metadata["sample_digest"],
        "fallback_policy": metadata["fallback_policy"],
        "area_count": len(metadata["areas"]),
        "artifact_hash": metadata["artifact_hash"],
    }
