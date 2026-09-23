from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import sparse
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler, normalize

from pipeline.clustering.experiments import sha256_file
from pipeline.features.areas import assign_rows, load_area_artifact

PERSONALIZATION_ARTIFACT_VERSION = "phase3-taipei-personalization-v3"
NUMERIC_FEATURE_NAMES = (
    "median_distance_km",
    "p75_distance_km",
    "median_duration_min",
    "lunch_ratio",
    "dinner_ratio",
    "night_ratio",
    "weekend_ratio",
    "cross_area_ratio",
    "fare_midpoint_mean",
)


@dataclass(frozen=True)
class PersonalizationConfig:
    fit_split: str = "train"
    batch_size: int = 50_000
    full_trip_threshold: int = 10
    light_trip_threshold: int = 3
    max_neighbors: int = 50
    min_effective_neighbors: int = 5
    numeric_block_weight: float = 0.60
    area_block_weight: float = 0.40


@dataclass
class RiderAccumulator:
    trip_count: int = 0
    distances: list[float] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    fares: list[float] = field(default_factory=list)
    period_counts: Counter[str] = field(default_factory=Counter)
    weekday_counts: Counter[str] = field(default_factory=Counter)
    known_source_count: int = 0
    cross_area_count: int = 0
    area_counts: Counter[str] = field(default_factory=Counter)
    area_period_counts: Counter[tuple[str, str]] = field(default_factory=Counter)


def hash_rider_key(rider_id: int, salt: str) -> str:
    if not salt:
        raise ValueError("RIDER_HASH_SALT must be configured")
    digest = hmac.new(
        salt.encode("utf-8"),
        str(int(rider_id)).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"rider_{digest}"


def personalization_level(trip_count: int, config: PersonalizationConfig | None = None) -> str:
    config = config or PersonalizationConfig()
    if trip_count >= config.full_trip_threshold:
        return "full"
    if trip_count >= config.light_trip_threshold:
        return "light"
    return "cold"


def distance_fit(distance_km: float, p25_km: float, p75_km: float, p90_km: float) -> float:
    """Piecewise 0-1 fit: p25-p75 plateau, then decline through and after p90."""
    distance = max(float(distance_km), 0.0)
    p25 = max(float(p25_km), 0.1)
    p75 = max(float(p75_km), p25)
    p90 = max(float(p90_km), p75 + 0.1)
    if distance < p25:
        return float(np.clip(0.35 + 0.65 * (distance / p25), 0.0, 1.0))
    if distance <= p75:
        return 1.0
    if distance <= p90:
        return float(1.0 - 0.35 * ((distance - p75) / (p90 - p75)))
    return float(np.clip(0.65 * math.exp(-(distance - p90) / p90), 0.0, 1.0))


def _quantile(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    return float(np.quantile(np.asarray(values, dtype=np.float64), value))


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


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        path,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
    )


def _profile_record(
    rider_key: str,
    accumulator: RiderAccumulator,
    config: PersonalizationConfig,
) -> dict[str, Any]:
    count = accumulator.trip_count
    fare_mean = float(np.mean(accumulator.fares)) if accumulator.fares else None
    return {
        "rider_key": rider_key,
        "trip_count": count,
        "personalization_level": personalization_level(count, config),
        "p25_distance_km": _quantile(accumulator.distances, 0.25),
        "median_distance_km": _quantile(accumulator.distances, 0.50),
        "p75_distance_km": _quantile(accumulator.distances, 0.75),
        "p90_distance_km": _quantile(accumulator.distances, 0.90),
        "median_duration_min": _quantile(accumulator.durations, 0.50),
        "morning_ratio": accumulator.period_counts["morning"] / count,
        "lunch_ratio": accumulator.period_counts["lunch"] / count,
        "afternoon_ratio": accumulator.period_counts["afternoon"] / count,
        "dinner_ratio": accumulator.period_counts["dinner"] / count,
        "night_ratio": accumulator.period_counts["night"] / count,
        "weekend_ratio": accumulator.weekday_counts["weekend"] / count,
        "cross_area_ratio": (
            accumulator.cross_area_count / accumulator.known_source_count
            if accumulator.known_source_count
            else 0.0
        ),
        "fare_midpoint_mean": fare_mean,
        "effective_neighbor_count": 0,
    }


def _build_neighbors(
    full_profiles: list[dict[str, Any]],
    area_counts_by_key: dict[str, Counter[str]],
    area_ids: list[str],
    config: PersonalizationConfig,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, Any]]:
    if len(full_profiles) < 2:
        return [], {}, {"numeric_mean": [], "numeric_scale": []}

    fare_values = [
        float(profile["fare_midpoint_mean"])
        for profile in full_profiles
        if profile["fare_midpoint_mean"] is not None
    ]
    fare_fill = float(np.median(fare_values)) if fare_values else 0.0
    numeric = np.asarray(
        [
            [
                float(profile[name])
                if profile[name] is not None
                else fare_fill
                for name in NUMERIC_FEATURE_NAMES
            ]
            for profile in full_profiles
        ],
        dtype=np.float64,
    )
    scaler = StandardScaler()
    numeric_block = normalize(scaler.fit_transform(numeric), norm="l2")

    area_index = {area_id: index for index, area_id in enumerate(area_ids)}
    rows: list[int] = []
    columns: list[int] = []
    values: list[float] = []
    for row_index, profile in enumerate(full_profiles):
        for area_id, count in area_counts_by_key.get(profile["rider_key"], Counter()).items():
            column_index = area_index.get(area_id)
            if column_index is None or count <= 0:
                continue
            rows.append(row_index)
            columns.append(column_index)
            values.append(math.log1p(count))
    area_block = sparse.csr_matrix(
        (values, (rows, columns)),
        shape=(len(full_profiles), len(area_ids)),
        dtype=np.float64,
    )
    area_block = normalize(area_block, norm="l2")
    combined = sparse.hstack(
        [
            sparse.csr_matrix(numeric_block * config.numeric_block_weight),
            area_block * config.area_block_weight,
        ],
        format="csr",
    )
    combined = normalize(combined, norm="l2")

    requested = min(config.max_neighbors + 1, len(full_profiles))
    model = NearestNeighbors(metric="cosine", algorithm="brute", n_jobs=-1)
    model.fit(combined)
    distances, indices = model.kneighbors(combined, n_neighbors=requested)

    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for row_index, profile in enumerate(full_profiles):
        rider_key = profile["rider_key"]
        candidates: list[tuple[float, str]] = []
        for distance, neighbor_index in zip(distances[row_index], indices[row_index]):
            if int(neighbor_index) == row_index:
                continue
            similarity = max(1.0 - float(distance), 0.0)
            if similarity <= 0.0:
                continue
            neighbor_key = full_profiles[int(neighbor_index)]["rider_key"]
            candidates.append((similarity, neighbor_key))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        candidates = candidates[: config.max_neighbors]
        counts[rider_key] = len(candidates)
        for rank, (similarity, neighbor_key) in enumerate(candidates, start=1):
            records.append(
                {
                    "rider_key": rider_key,
                    "neighbor_rider_key": neighbor_key,
                    "similarity": round(similarity, 12),
                    "rank": rank,
                }
            )

    return records, counts, {
        "numeric_feature_names": list(NUMERIC_FEATURE_NAMES),
        "numeric_mean": scaler.mean_.tolist(),
        "numeric_scale": scaler.scale_.tolist(),
        "fare_fill": fare_fill,
        "numeric_block_weight": config.numeric_block_weight,
        "area_block_weight": config.area_block_weight,
    }


def build_personalization_artifact(
    input_path: Path,
    area_artifact_dir: Path,
    output_dir: Path,
    rider_hash_salt: str,
    config: PersonalizationConfig | None = None,
) -> dict[str, Any]:
    config = config or PersonalizationConfig()
    if config.fit_split != "train":
        raise ValueError("personalization features must fit on Train")
    if not rider_hash_salt:
        raise ValueError("RIDER_HASH_SALT must be configured before personalization")

    input_path = input_path.resolve()
    area = load_area_artifact(area_artifact_dir)
    area_metadata = area["metadata"]
    input_sha256 = sha256_file(input_path)
    if area_metadata["input_sha256"] != input_sha256:
        raise ValueError("personalization input does not match area artifact input")

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / "personalization_artifact.json"
    profiles_path = output_dir / "rider_profiles.parquet"
    area_stats_path = output_dir / "rider_area_stats.parquet"
    neighbors_path = output_dir / "rider_neighbors.parquet"
    report_path = output_dir / "personalization_artifact.md"
    salt_fingerprint = hashlib.sha256(rider_hash_salt.encode("utf-8")).hexdigest()[:16]
    expected = {
        "artifact_version": PERSONALIZATION_ARTIFACT_VERSION,
        "input_sha256": input_sha256,
        "area_artifact_hash": area_metadata["artifact_hash"],
        "salt_fingerprint": salt_fingerprint,
        "config": asdict(config),
    }
    if metadata_path.exists() and all(path.exists() for path in (profiles_path, area_stats_path, neighbors_path)):
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if all(existing.get(key) == value for key, value in expected.items()):
            return {
                "metadata": existing,
                "paths": {
                    "metadata": metadata_path,
                    "profiles": profiles_path,
                    "area_stats": area_stats_path,
                    "neighbors": neighbors_path,
                    "report": report_path,
                },
            }

    riders: dict[int, RiderAccumulator] = defaultdict(RiderAccumulator)
    rows_read = 0
    eligible_rows = 0
    parquet = pq.ParquetFile(input_path)
    columns = [
        "rider_id",
        "period",
        "weekday_class",
        "distance_km",
        "travel_time_min",
        "fare_midpoint",
        "model_eligible",
        "pickup_lat",
        "pickup_lng",
        "dropoff_lat",
        "dropoff_lng",
        "split",
    ]
    cluster_to_area = area_metadata["cluster_to_area"]
    for batch in parquet.iter_batches(columns=columns, batch_size=config.batch_size):
        batch_rows = [row for row in batch.to_pylist() if row["split"] == config.fit_split]
        rows_read += len(batch_rows)
        eligible = [row for row in batch_rows if bool(row["model_eligible"])]
        if not eligible:
            continue
        eligible_rows += len(eligible)
        pickups, dropoffs = assign_rows(
            area["model"],
            [(float(row["pickup_lat"]), float(row["pickup_lng"])) for row in eligible],
            [(float(row["dropoff_lat"]), float(row["dropoff_lng"])) for row in eligible],
            cluster_to_area,
        )
        for row, pickup, dropoff in zip(eligible, pickups, dropoffs):
            accumulator = riders[int(row["rider_id"])]
            accumulator.trip_count += 1
            accumulator.distances.append(float(row["distance_km"]))
            accumulator.durations.append(float(row["travel_time_min"]))
            if row["fare_midpoint"] is not None:
                accumulator.fares.append(float(row["fare_midpoint"]))
            period = str(row["period"])
            accumulator.period_counts[period] += 1
            accumulator.weekday_counts[str(row["weekday_class"])] += 1
            if pickup.source == "model" and dropoff.source == "model":
                accumulator.known_source_count += 1
                if pickup.area_id != dropoff.area_id:
                    accumulator.cross_area_count += 1
            if dropoff.source == "model" and dropoff.region == "Taipei":
                accumulator.area_counts[dropoff.area_id] += 1
                accumulator.area_period_counts[(dropoff.area_id, period)] += 1

    profile_records: list[dict[str, Any]] = []
    area_stat_records: list[dict[str, Any]] = []
    area_counts_by_key: dict[str, Counter[str]] = {}
    all_area_period_log_counts: list[float] = []
    cohort_distances: dict[str, list[float]] = defaultdict(list)
    for rider_id in sorted(riders):
        accumulator = riders[rider_id]
        rider_key = hash_rider_key(rider_id, rider_hash_salt)
        level = personalization_level(accumulator.trip_count, config)
        cohort_distances[level].extend(accumulator.distances)
        if level == "cold":
            continue
        profile_records.append(_profile_record(rider_key, accumulator, config))
        area_counts_by_key[rider_key] = accumulator.area_counts
        for (area_id, period), count in sorted(accumulator.area_period_counts.items()):
            area_stat_records.append(
                {
                    "rider_key": rider_key,
                    "area_id": area_id,
                    "period": period,
                    "visit_count": int(count),
                    "visit_ratio": count / accumulator.trip_count,
                }
            )
            all_area_period_log_counts.append(math.log1p(count))

    profile_records.sort(key=lambda row: row["rider_key"])
    area_stat_records.sort(key=lambda row: (row["rider_key"], row["area_id"], row["period"]))
    full_profiles = [row for row in profile_records if row["personalization_level"] == "full"]
    area_ids = sorted(item["area_id"] for item in area_metadata["areas"])
    neighbor_records, neighbor_counts, similarity_metadata = _build_neighbors(
        full_profiles,
        area_counts_by_key,
        area_ids,
        config,
    )
    for profile in profile_records:
        profile["effective_neighbor_count"] = neighbor_counts.get(profile["rider_key"], 0)

    full_candidates = sorted(
        (
            row for row in profile_records
            if row["personalization_level"] == "full"
            and row["effective_neighbor_count"] >= config.min_effective_neighbors
        ),
        key=lambda row: (-int(row["trip_count"]), row["rider_key"]),
    )
    light_candidates = sorted(
        (row for row in profile_records if row["personalization_level"] == "light"),
        key=lambda row: (-int(row["trip_count"]), row["rider_key"]),
    )
    demo_aliases = {
        "demo_rider_01": full_candidates[0]["rider_key"] if full_candidates else None,
        "demo_rider_02": light_candidates[0]["rider_key"] if light_candidates else None,
        "demo_rider_cold": None,
    }

    b_scale = {
        "p5": _quantile(all_area_period_log_counts, 0.05),
        "p95": _quantile(all_area_period_log_counts, 0.95),
    }
    cohort_distance_reference = {
        level: {
            "p25": _quantile(values, 0.25),
            "median": _quantile(values, 0.50),
            "p75": _quantile(values, 0.75),
            "p90": _quantile(values, 0.90),
        }
        for level, values in sorted(cohort_distances.items())
    }

    _write_parquet(profiles_path, profile_records)
    _write_parquet(area_stats_path, area_stat_records)
    _write_parquet(neighbors_path, neighbor_records)
    output_hashes = {
        "profiles_sha256": sha256_file(profiles_path),
        "area_stats_sha256": sha256_file(area_stats_path),
        "neighbors_sha256": sha256_file(neighbors_path),
    }
    level_counts = Counter(row["personalization_level"] for row in profile_records)
    cold_rider_count = sum(1 for value in riders.values() if value.trip_count < config.light_trip_threshold)
    metadata = {
        **expected,
        "fit_split": config.fit_split,
        "scope": "Taipei Demo only",
        "rows_read": rows_read,
        "eligible_rows": eligible_rows,
        "rider_counts": {
            "full": level_counts["full"],
            "light": level_counts["light"],
            "cold": cold_rider_count,
            "total": len(riders),
        },
        "profile_count": len(profile_records),
        "rider_area_stat_count": len(area_stat_records),
        "neighbor_count": len(neighbor_records),
        "b_scale": b_scale,
        "cohort_distance_reference": cohort_distance_reference,
        "similarity": similarity_metadata,
        "demo_aliases": demo_aliases,
        "output_hashes": output_hashes,
        "artifact_hash": None,
    }
    metadata["artifact_hash"] = _json_digest(
        {key: value for key, value in metadata.items() if key != "artifact_hash"}
    )
    _write_json(metadata_path, metadata)
    report_path.write_text(
        "\n".join(
            [
                "# Taipei Demo personalization artifact",
                "",
                "所有輸出使用 salted rider_key；不保存或顯示 RiderId、TripId 與 raw rows。",
                "",
                f"- fit_split: {config.fit_split}",
                f"- eligible Train rows: {eligible_rows}",
                f"- riders: {len(riders)}",
                f"- full profiles: {level_counts['full']}",
                f"- light profiles: {level_counts['light']}",
                f"- cold riders: {cold_rider_count}",
                f"- neighbor rows: {len(neighbor_records)}",
                f"- artifact_hash: {metadata['artifact_hash']}",
                "",
                "B 只有 full rider 且有效鄰居至少 5 人時可用；其他情況必須標記 unavailable 並重新分配權重。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "metadata": metadata,
        "paths": {
            "metadata": metadata_path,
            "profiles": profiles_path,
            "area_stats": area_stats_path,
            "neighbors": neighbors_path,
            "report": report_path,
        },
    }


def load_personalization_artifact(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    return {
        "metadata": json.loads((output_dir / "personalization_artifact.json").read_text(encoding="utf-8")),
        "profiles": pq.read_table(output_dir / "rider_profiles.parquet").to_pylist(),
        "area_stats": pq.read_table(output_dir / "rider_area_stats.parquet").to_pylist(),
        "neighbors": pq.read_table(output_dir / "rider_neighbors.parquet").to_pylist(),
    }
