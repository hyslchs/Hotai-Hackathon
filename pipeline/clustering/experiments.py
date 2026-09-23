from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import platform
import threading
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import hdbscan
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import psutil
import pyarrow.parquet as pq

warnings.filterwarnings("ignore", message=".*force_all_finite.*")
warnings.filterwarnings("ignore", message="Clusterer does not have any defined clusters.*")

from .geometry import (
    CITY_REGIONS,
    deterministic_stratified_sample,
    points_digest,
    region_for_point,
)


Point = tuple[float, float, str]
REQUIRED_COLUMNS = (
    "split",
    "model_eligible",
    "pickup_lat",
    "pickup_lng",
    "dropoff_lat",
    "dropoff_lng",
)
DEFAULT_SAMPLE_SIZES = (50_000, 100_000, 200_000)
DEFAULT_MIN_CLUSTER_SIZES = (50, 100, 250, 500)
DEFAULT_MIN_SAMPLES = (10, 25, 50)
PREVIEW_PARAMS = (250, 25, "eom")


@dataclass(frozen=True)
class ExperimentConfig:
    sample_sizes: tuple[int, ...] = DEFAULT_SAMPLE_SIZES
    min_cluster_sizes: tuple[int, ...] = DEFAULT_MIN_CLUSTER_SIZES
    min_samples: tuple[int, ...] = DEFAULT_MIN_SAMPLES
    cluster_selection_methods: tuple[str, ...] = ("eom",)
    batch_size: int = 50_000
    assignment_sample_per_endpoint: int = 1_000
    seed: int = 20260918


class PeakRSS:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.stop_event = threading.Event()
        self.peak = self.process.memory_info().rss
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop_event.wait(0.05):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self) -> "PeakRSS":
        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1.0)
        self.peak = max(self.peak, self.process.memory_info().rss)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_coordinate_pool(
    parquet_path: Path,
    include_soft_outliers: bool,
    split: str = "train",
    batch_size: int = 50_000,
) -> list[Point]:
    pool: list[Point] = []
    parquet = pq.ParquetFile(parquet_path)
    for batch in parquet.iter_batches(columns=list(REQUIRED_COLUMNS), batch_size=batch_size):
        for row in batch.to_pylist():
            if row["split"] != split:
                continue
            if not include_soft_outliers and not bool(row["model_eligible"]):
                continue
            pickup_lat = float(row["pickup_lat"])
            pickup_lng = float(row["pickup_lng"])
            dropoff_lat = float(row["dropoff_lat"])
            dropoff_lng = float(row["dropoff_lng"])
            pool.append((pickup_lat, pickup_lng, region_for_point(pickup_lat, pickup_lng)))
            pool.append((dropoff_lat, dropoff_lng, region_for_point(dropoff_lat, dropoff_lng)))
    return pool


def load_endpoint_samples(
    parquet_path: Path,
    include_soft_outliers: bool,
    split: str,
    max_per_endpoint: int,
    batch_size: int = 50_000,
) -> tuple[list[Point], list[Point]]:
    pickups: list[Point] = []
    dropoffs: list[Point] = []
    parquet = pq.ParquetFile(parquet_path)
    for batch in parquet.iter_batches(columns=list(REQUIRED_COLUMNS), batch_size=batch_size):
        for row in batch.to_pylist():
            if row["split"] != split:
                continue
            if not include_soft_outliers and not bool(row["model_eligible"]):
                continue
            pickup = (
                float(row["pickup_lat"]),
                float(row["pickup_lng"]),
                region_for_point(float(row["pickup_lat"]), float(row["pickup_lng"])),
            )
            dropoff = (
                float(row["dropoff_lat"]),
                float(row["dropoff_lng"]),
                region_for_point(float(row["dropoff_lat"]), float(row["dropoff_lng"])),
            )
            if len(pickups) < max_per_endpoint:
                pickups.append(pickup)
            if len(dropoffs) < max_per_endpoint:
                dropoffs.append(dropoff)
            if len(pickups) >= max_per_endpoint and len(dropoffs) >= max_per_endpoint:
                return pickups, dropoffs
    return pickups, dropoffs


def to_haversine_array(points: Sequence[Point]) -> np.ndarray:
    if not points:
        return np.empty((0, 2), dtype=np.float64)
    degrees = np.asarray([(point[0], point[1]) for point in points], dtype=np.float64)
    return np.radians(degrees)


def _quantile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), quantile))


def _cluster_radii_km(points: Sequence[Point], labels: np.ndarray) -> list[float]:
    coordinates = np.asarray([(point[0], point[1]) for point in points], dtype=np.float64)
    radii: list[float] = []
    for cluster_id in sorted(int(value) for value in np.unique(labels) if int(value) >= 0):
        members = coordinates[labels == cluster_id]
        if len(members) == 0:
            continue
        center_lat = float(np.mean(members[:, 0]))
        center_lng = float(np.mean(members[:, 1]))
        lat_a = np.radians(members[:, 0])
        lng_a = np.radians(members[:, 1])
        lat_b = math.radians(center_lat)
        lng_b = math.radians(center_lng)
        delta_lat = lat_b - lat_a
        delta_lng = lng_b - lng_a
        haversine = (
            np.sin(delta_lat / 2.0) ** 2
            + np.cos(lat_a) * math.cos(lat_b) * np.sin(delta_lng / 2.0) ** 2
        )
        distances = 2.0 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))
        radii.append(float(np.quantile(distances, 0.90)))
    return radii


def cluster_metrics(
    points: Sequence[Point],
    labels: np.ndarray,
    elapsed_seconds: float,
    peak_rss_bytes: int,
) -> dict[str, Any]:
    labels = np.asarray(labels, dtype=np.int64)
    non_noise = labels >= 0
    cluster_sizes = [
        int(np.count_nonzero(labels == cluster_id))
        for cluster_id in sorted(int(value) for value in np.unique(labels) if int(value) >= 0)
    ]
    radii = _cluster_radii_km(points, labels)
    city_coverage: dict[str, float] = {}
    city_counts: dict[str, int] = {}
    for region in CITY_REGIONS:
        indexes = [index for index, point in enumerate(points) if point[2] == region]
        city_counts[region] = len(indexes)
        city_coverage[region] = (
            float(np.count_nonzero(non_noise[indexes])) / len(indexes)
            if indexes
            else 0.0
        )
    return {
        "point_count": int(len(points)),
        "cluster_count": int(len(cluster_sizes)),
        "noise_count": int(np.count_nonzero(~non_noise)),
        "noise_ratio": float(np.mean(~non_noise)) if len(labels) else 0.0,
        "cluster_size_min": min(cluster_sizes) if cluster_sizes else 0,
        "cluster_size_p50": _quantile(cluster_sizes, 0.50),
        "cluster_size_p90": _quantile(cluster_sizes, 0.90),
        "cluster_size_max": max(cluster_sizes) if cluster_sizes else 0,
        "equivalent_radius_km_p50": _quantile(radii, 0.50),
        "equivalent_radius_km_p90": _quantile(radii, 0.90),
        "equivalent_radius_km_max": max(radii) if radii else None,
        "city_point_counts": city_counts,
        "city_assignment_coverage": city_coverage,
        "fit_seconds": float(elapsed_seconds),
        "peak_rss_mb": round(float(peak_rss_bytes) / (1024.0 * 1024.0), 3),
    }


def fit_candidate(
    points: Sequence[Point],
    min_cluster_size: int,
    min_samples: int,
    cluster_selection_method: str,
) -> tuple[Any, np.ndarray, dict[str, Any]]:
    coordinates = to_haversine_array(points)
    model = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="haversine",
        cluster_selection_method=cluster_selection_method,
        prediction_data=True,
        core_dist_n_jobs=1,
    )
    started = time.perf_counter()
    with PeakRSS() as memory:
        labels = model.fit_predict(coordinates)
    elapsed = time.perf_counter() - started
    metrics = cluster_metrics(points, labels, elapsed, memory.peak)
    return model, np.asarray(labels, dtype=np.int64), metrics


def assignment_metrics(model: Any, points: Sequence[Point]) -> dict[str, Any]:
    if not points:
        return {"point_count": 0, "assigned_count": 0, "assignment_coverage": 0.0}
    labels, strengths = hdbscan.approximate_predict(model, to_haversine_array(points))
    del strengths
    labels = np.asarray(labels, dtype=np.int64)
    assigned = labels >= 0
    return {
        "point_count": int(len(points)),
        "assigned_count": int(np.count_nonzero(assigned)),
        "assignment_coverage": float(np.mean(assigned)),
    }


def write_city_maps(
    points: Sequence[Point],
    labels: np.ndarray,
    output_path: Path,
    title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 3, figsize=(18, 6), constrained_layout=True)
    labels = np.asarray(labels, dtype=np.int64)
    colors = np.where(labels < 0, -1, labels % 20)
    for axis, region in zip(axes, ("Taipei", "Taichung", "Kaohsiung")):
        indexes = [index for index, point in enumerate(points) if point[2] == region]
        if len(indexes) > 20_000:
            indexes = indexes[:20_000]
        if indexes:
            selected = np.asarray(indexes, dtype=np.int64)
            axis.scatter(
                [points[index][1] for index in indexes],
                [points[index][0] for index in indexes],
                c=colors[selected],
                s=1,
                alpha=0.35,
                cmap="tab20",
                vmin=-1,
                vmax=19,
            )
        axis.set_title(region)
        axis.set_xlabel("longitude")
        axis.set_ylabel("latitude")
        axis.grid(alpha=0.2)
    figure.suptitle(title)
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        candidate["policy"],
        candidate["sample_size"],
        candidate["min_cluster_size"],
        candidate["min_samples"],
        candidate["cluster_selection_method"],
    )


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 geographic-area experiment",
        "",
        "本報告只呈現 aggregate metrics，不包含 RiderId、TripId、POI 原文或 raw rows。",
        "",
        "## Scope and policy comparison",
        "",
        f"- Input: {report['input']['path']}",
        f"- Fit split: {report['config']['fit_split']}",
        f"- Eligible-only coordinate points: {report['policy_counts']['eligible_only']['point_count']}",
        f"- All-train coordinate points: {report['policy_counts']['all_train']['point_count']}",
        "",
        "soft-outlier 仍保留在 clean artifact；eligible_only 只把 model_eligible=true 的 Train rows 放入 coordinate pool。",
        "",
        "## Candidate results",
        "",
        "| policy | sample | min_cluster_size | min_samples | clusters | noise | radius p90 km | Taipei | Taichung | Kaohsiung | seconds | peak MB | status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for candidate in report["candidates"]:
        metrics = candidate.get("metrics", {})
        coverage = metrics.get("city_assignment_coverage", {})
        lines.append(
            "| {policy} | {sample_size} | {min_cluster_size} | {min_samples} | {cluster_count} | {noise_ratio:.4f} | {radius} | {taipei:.4f} | {taichung:.4f} | {kaohsiung:.4f} | {seconds:.2f} | {peak:.1f} | {status} |".format(
                policy=candidate["policy"],
                sample_size=candidate["sample_size"],
                min_cluster_size=candidate["min_cluster_size"],
                min_samples=candidate["min_samples"],
                cluster_count=metrics.get("cluster_count", "-"),
                noise_ratio=metrics.get("noise_ratio", 0.0),
                radius=(
                    f"{metrics['equivalent_radius_km_p90']:.3f}"
                    if metrics.get("equivalent_radius_km_p90") is not None
                    else "-"
                ),
                taipei=coverage.get("Taipei", 0.0),
                taichung=coverage.get("Taichung", 0.0),
                kaohsiung=coverage.get("Kaohsiung", 0.0),
                seconds=metrics.get("fit_seconds", 0.0),
                peak=metrics.get("peak_rss_mb", 0.0),
                status=candidate["status"],
            )
        )
    lines.extend(["", "## Assignment smoke tests", ""])
    for policy, values in report["assignments"].items():
        lines.append(f"### {policy}")
        lines.append("")
        lines.append(f"- fit_split: {values['fit_split']}")
        lines.append(f"- fit_refit_for_assignment: {values['fit_refit_for_assignment']}")
        for split, endpoints in values["splits"].items():
            lines.append(
                f"- {split}: pickup coverage {endpoints['pickup']['assignment_coverage']:.4f}, "
                f"dropoff coverage {endpoints['dropoff']['assignment_coverage']:.4f}"
            )
        lines.append("")
    lines.extend(
        [
            "## Soft-outlier sensitivity",
            "",
            "這是同一組 provisional preview parameters 的比較，不是正式最佳模型選擇。",
        ]
    )
    for row in report["sensitivity"]:
        lines.append(
            f"- sample {row['sample_size']}: cluster_count_delta={row['cluster_count_delta']}, "
            f"noise_ratio_delta={row['noise_ratio_delta']:.6f}, "
            f"Taipei_coverage_delta={row['Taipei_coverage_delta']:.6f}, "
            f"Taichung_coverage_delta={row['Taichung_coverage_delta']:.6f}, "
            f"Kaohsiung_coverage_delta={row['Kaohsiung_coverage_delta']:.6f}"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Cluster selection remains a human decision.",
            "- Preview maps use min_cluster_size=250, min_samples=25, eom only for visual inspection.",
            "- Validation and Test are assigned after fit and never participate in fitting.",
            "- Soft-outlier policy must be revisited if downstream feature evidence shows dimension-specific eligibility is needed.",
        ]
    )
    return "\n".join(lines) + "\n"


def _canonical_metrics(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "policy",
        "sample_size",
        "min_cluster_size",
        "min_samples",
        "cluster_selection_method",
        "status",
        "metrics",
    )
    canonical: list[dict[str, Any]] = []
    for candidate in candidates:
        selected = {field: candidate.get(field) for field in fields}
        if isinstance(selected.get("metrics"), dict):
            selected["metrics"] = {
                key: value
                for key, value in selected["metrics"].items()
                if key not in {"fit_seconds", "peak_rss_mb"}
            }
        canonical.append(selected)
    return canonical


def _json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_experiments(
    input_path: Path,
    output_dir: Path,
    config: ExperimentConfig | None = None,
) -> dict[str, Any]:
    config = config or ExperimentConfig()
    input_path = input_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    maps_dir = output_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    policy_flags = {"eligible_only": False, "all_train": True}
    pools: dict[str, list[Point]] = {}
    policy_counts: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    preview_models: dict[str, tuple[Any, list[Point], np.ndarray]] = {}

    for policy, include_soft_outliers in policy_flags.items():
        pool = load_coordinate_pool(
            input_path,
            include_soft_outliers=include_soft_outliers,
            split="train",
            batch_size=config.batch_size,
        )
        pools[policy] = pool
        policy_counts[policy] = {
            "point_count": len(pool),
            "point_digest": points_digest(pool),
        }
        print(f"phase2_pool policy={policy} points={len(pool)}")

        for sample_size in config.sample_sizes:
            if sample_size > len(pool):
                for min_cluster_size in config.min_cluster_sizes:
                    for min_samples in config.min_samples:
                        for method in config.cluster_selection_methods:
                            candidates.append(
                                {
                                    "policy": policy,
                                    "sample_size": sample_size,
                                    "min_cluster_size": min_cluster_size,
                                    "min_samples": min_samples,
                                    "cluster_selection_method": method,
                                    "status": "skipped",
                                    "error": "sample_size_exceeds_coordinate_pool",
                                }
                            )
                continue
            sample = deterministic_stratified_sample(pool, sample_size)
            for min_cluster_size in config.min_cluster_sizes:
                for min_samples in config.min_samples:
                    for method in config.cluster_selection_methods:
                        candidate = {
                            "policy": policy,
                            "sample_size": sample_size,
                            "min_cluster_size": min_cluster_size,
                            "min_samples": min_samples,
                            "cluster_selection_method": method,
                            "status": "completed",
                        }
                        try:
                            model, labels, metrics = fit_candidate(
                                sample,
                                min_cluster_size,
                                min_samples,
                                method,
                            )
                            candidate["metrics"] = metrics
                            candidate["sample_digest"] = points_digest(sample)
                            if sample_size == max(config.sample_sizes) and (
                                min_cluster_size,
                                min_samples,
                                method,
                            ) == PREVIEW_PARAMS:
                                preview_models[policy] = (model, sample, labels)
                            else:
                                del model
                            del labels
                            gc.collect()
                            print(
                                "phase2_candidate "
                                f"policy={policy} sample={sample_size} "
                                f"min_cluster_size={min_cluster_size} min_samples={min_samples} "
                                f"clusters={metrics['cluster_count']} noise={metrics['noise_ratio']:.4f}"
                            )
                        except Exception as error:
                            candidate["status"] = "failed"
                            candidate["error"] = type(error).__name__
                            print(
                                "phase2_candidate_failed "
                                f"policy={policy} sample={sample_size} "
                                f"min_cluster_size={min_cluster_size} min_samples={min_samples} "
                                f"error={type(error).__name__}"
                            )
                        candidates.append(candidate)

    assignments: dict[str, Any] = {}
    map_paths: list[str] = []
    for policy, preview in preview_models.items():
        model, sample, labels = preview
        map_path = maps_dir / f"{policy}_preview_200k.png"
        write_city_maps(sample, labels, map_path, f"{policy} preview, 200k, fixed parameters")
        map_paths.append(str(map_path.relative_to(output_dir)).replace("\\", "/"))

        split_assignments: dict[str, Any] = {}
        for split in ("train", "validation", "test"):
            pickups, dropoffs = load_endpoint_samples(
                input_path,
                include_soft_outliers=policy_flags[policy],
                split=split,
                max_per_endpoint=config.assignment_sample_per_endpoint,
                batch_size=config.batch_size,
            )
            split_assignments[split] = {
                "pickup": assignment_metrics(model, pickups),
                "dropoff": assignment_metrics(model, dropoffs),
            }
        assignments[policy] = {
            "fit_split": "train",
            "fit_refit_for_assignment": False,
            "preview_parameters": {
                "min_cluster_size": PREVIEW_PARAMS[0],
                "min_samples": PREVIEW_PARAMS[1],
                "cluster_selection_method": PREVIEW_PARAMS[2],
            },
            "splits": split_assignments,
        }
        del model, sample, labels
        gc.collect()

    sensitivity: list[dict[str, Any]] = []
    preview_candidates = [
        candidate
        for candidate in candidates
        if candidate["status"] == "completed"
        and candidate["min_cluster_size"] == PREVIEW_PARAMS[0]
        and candidate["min_samples"] == PREVIEW_PARAMS[1]
        and candidate["cluster_selection_method"] == PREVIEW_PARAMS[2]
    ]
    by_size = {(candidate["policy"], candidate["sample_size"]): candidate for candidate in preview_candidates}
    for sample_size in config.sample_sizes:
        eligible = by_size.get(("eligible_only", sample_size))
        all_train = by_size.get(("all_train", sample_size))
        if not eligible or not all_train:
            continue
        eligible_metrics = eligible["metrics"]
        all_metrics = all_train["metrics"]
        eligible_coverage = eligible_metrics["city_assignment_coverage"]
        all_coverage = all_metrics["city_assignment_coverage"]
        sensitivity.append(
            {
                "sample_size": sample_size,
                "cluster_count_delta": all_metrics["cluster_count"] - eligible_metrics["cluster_count"],
                "noise_ratio_delta": all_metrics["noise_ratio"] - eligible_metrics["noise_ratio"],
                "Taipei_coverage_delta": all_coverage["Taipei"] - eligible_coverage["Taipei"],
                "Taichung_coverage_delta": all_coverage["Taichung"] - eligible_coverage["Taichung"],
                "Kaohsiung_coverage_delta": all_coverage["Kaohsiung"] - eligible_coverage["Kaohsiung"],
            }
        )

    report: dict[str, Any] = {
        "report_version": "phase2-geographic-v1",
        "input": {
            "path": str(input_path.relative_to(Path.cwd())).replace("\\", "/")
            if input_path.is_relative_to(Path.cwd())
            else input_path.name,
            "sha256": sha256_file(input_path),
        },
        "config": {
            "fit_split": "train",
            **asdict(config),
        },
        "policy_counts": policy_counts,
        "candidates": candidates,
        "assignments": assignments,
        "sensitivity": sensitivity,
        "maps": sorted(map_paths),
        "limitations": [
            "Candidate selection is not finalized.",
            "Preview maps are visual checks only.",
            "All metrics are derived from Train coordinate samples.",
        ],
    }
    report["canonical_metrics_sha256"] = _json_digest(_canonical_metrics(candidates))
    report_json_path = output_dir / "phase2_report.json"
    report_md_path = output_dir / "phase2_report.md"
    report_json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(markdown_report(report), encoding="utf-8")

    manifest: dict[str, Any] = {
        "manifest_version": "phase2-manifest-v1",
        "input_sha256": report["input"]["sha256"],
        "config": report["config"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "completed_candidates": sum(candidate["status"] == "completed" for candidate in candidates),
        "failed_candidates": sum(candidate["status"] == "failed" for candidate in candidates),
        "skipped_candidates": sum(candidate["status"] == "skipped" for candidate in candidates),
        "canonical_metrics_sha256": report["canonical_metrics_sha256"],
        "artifacts": {
            "phase2_report.json": {
                "path": "data/clustering/phase2/phase2_report.json",
                "sha256": sha256_file(report_json_path),
            },
            "phase2_report.md": {
                "path": "data/clustering/phase2/phase2_report.md",
                "sha256": sha256_file(report_md_path),
            },
        },
    }
    manifest_path = output_dir / "phase2_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_sample_sizes(value: str) -> tuple[int, ...]:
    sizes = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("sample sizes must be positive integers")
    return sizes


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run Phase 2 geographic-area experiments")
    parser.add_argument("--input", type=Path, default=root / "data/processed/trips_clean.parquet")
    parser.add_argument("--output", type=Path, default=root / "data/clustering/phase2")
    parser.add_argument("--sample-sizes", default="50000,100000,200000")
    args = parser.parse_args(argv)
    config = ExperimentConfig(sample_sizes=parse_sample_sizes(args.sample_sizes))
    report = run_experiments(args.input, args.output, config)
    print(f"phase2_complete candidates={len(report['candidates'])}")
    print(f"phase2_report={args.output / 'phase2_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
