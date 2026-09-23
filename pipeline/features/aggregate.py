from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from .areas import assign_rows, load_area_artifact

PERIODS = ("morning", "lunch", "afternoon", "dinner", "night")
WEEKDAY_CLASSES = ("weekday", "weekend")
FEATURE_ARTIFACT_VERSION = "phase3-taipei-features-v1"
METRIC_NAMES = (
    "visit_heat",
    "period_lift",
    "cross_area_ratio",
    "source_diversity",
    "return_rate",
)


@dataclass(frozen=True)
class FeatureBuildConfig:
    fit_split: str = "train"
    smoothing_alpha: float = 1.0
    batch_size: int = 50_000


def context_key(period: str, weekday_class: str) -> str:
    return f"{period}|{weekday_class}"


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


def robust_scale_params(values: list[float]) -> dict[str, float | bool]:
    if not values:
        return {"p5": 0.0, "p95": 0.0, "constant": True}
    array = np.asarray(values, dtype=np.float64)
    p5 = float(np.quantile(array, 0.05))
    p95 = float(np.quantile(array, 0.95))
    return {
        "p5": p5,
        "p95": p95,
        "constant": math.isclose(p5, p95, rel_tol=0.0, abs_tol=1e-12),
    }


def robust_minmax(value: float, params: dict[str, float | bool]) -> float:
    if bool(params["constant"]):
        return 0.0
    p5 = float(params["p5"])
    p95 = float(params["p95"])
    return float(np.clip((value - p5) / (p95 - p5), 0.0, 1.0))


def normalized_entropy(counts: Counter[str]) -> float:
    nonzero = [count for count in counts.values() if count > 0]
    if len(nonzero) < 2:
        return 0.0
    total = float(sum(nonzero))
    probabilities = np.asarray([count / total for count in nonzero], dtype=np.float64)
    entropy = -float(np.sum(probabilities * np.log(probabilities)))
    return float(entropy / math.log(len(nonzero)))


def _area_rows(
    area_ids: list[str],
    context_counts: Counter[tuple[str, str, str]],
    context_totals: Counter[tuple[str, str]],
    area_totals: Counter[str],
    area_day_counts: dict[tuple[str, str, str], set[str]],
    source_counts: Counter[tuple[str, str]],
    known_source_counts: Counter[str],
    rider_visits: dict[str, Counter[int]],
    train_day_count: int,
    alpha: float,
) -> list[dict[str, Any]]:
    total_area_visits = sum(area_totals.values())
    rows: list[dict[str, Any]] = []
    for area_id in area_ids:
        area_probability = (area_totals[area_id] + alpha) / (
            total_area_visits + alpha * len(area_ids)
        )
        riders = rider_visits.get(area_id, Counter())
        rider_count = len(riders)
        repeat_count = sum(1 for visits in riders.values() if visits >= 2)
        return_rate = repeat_count / rider_count if rider_count else 0.0
        for period in PERIODS:
            for weekday_class in WEEKDAY_CLASSES:
                key = (area_id, period, weekday_class)
                count = context_counts[key]
                context_total = context_totals[(period, weekday_class)]
                context_probability = (count + alpha) / (
                    context_total + alpha * len(area_ids)
                )
                period_lift = math.log(
                    max(context_probability, 1e-12)
                    / max(area_probability, 1e-12)
                )
                known_source = known_source_counts[area_id]
                cross_area = sum(
                    value
                    for (destination, source), value in source_counts.items()
                    if destination == area_id and source != destination
                )
                source_ratio = cross_area / known_source if known_source else 0.0
                source_distribution = Counter(
                    {
                        source: value
                        for (destination, source), value in source_counts.items()
                        if destination == area_id
                    }
                )
                rows.append(
                    {
                        "area_id": area_id,
                        "period": period,
                        "weekday_class": weekday_class,
                        "context_key": context_key(period, weekday_class),
                        "visit_count": count,
                        "daily_visit_mean": count / max(train_day_count, 1),
                        "days_with_visits": len(area_day_counts.get(key, set())),
                        "visit_heat_raw": math.log1p(
                            count / max(train_day_count, 1)
                        ),
                        "period_lift_raw": period_lift,
                        "cross_area_ratio_raw": source_ratio,
                        "source_diversity_raw": normalized_entropy(source_distribution),
                        "return_rate_raw": return_rate,
                        "rider_count": rider_count,
                        "repeat_rider_count": repeat_count,
                    }
                )
    return rows


def _ranked_counts(
    counts: Counter[tuple[str, ...]],
    *,
    include_origin: bool,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    result: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(dict)
    for key, count in counts.items():
        if include_origin:
            origin_area, period, weekday_class, destination_area = key
            result[origin_area].setdefault(
                context_key(period, weekday_class), []
            ).append({"area_id": destination_area, "count": int(count)})
        else:
            period, weekday_class, destination_area = key
            result["all"].setdefault(
                context_key(period, weekday_class), []
            ).append({"area_id": destination_area, "count": int(count)})
    for origin_values in result.values():
        for values in origin_values.values():
            values.sort(key=lambda item: (-item["count"], item["area_id"]))
    return dict(result)


def _assign_batch(
    model: Any,
    cluster_to_area: dict[str, str],
    rows: list[dict[str, Any]],
) -> tuple[list[Any], list[Any]]:
    pickup_points = [
        (float(row["pickup_lat"]), float(row["pickup_lng"])) for row in rows
    ]
    dropoff_points = [
        (float(row["dropoff_lat"]), float(row["dropoff_lng"])) for row in rows
    ]
    return assign_rows(model, pickup_points, dropoff_points, cluster_to_area)


def build_taipei_features(
    input_path: Path,
    area_artifact_dir: Path,
    output_dir: Path,
    config: FeatureBuildConfig | None = None,
) -> dict[str, Any]:
    config = config or FeatureBuildConfig()
    input_path = input_path.resolve()
    area = load_area_artifact(area_artifact_dir)
    metadata = area["metadata"]
    if metadata["input_sha256"] != _file_sha256(input_path):
        raise ValueError("feature input does not match the frozen area artifact input")
    if config.fit_split != "train":
        raise ValueError("Phase 3 feature fit must use Train")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "feature_artifact.json"
    report_path = output_dir / "feature_artifact.md"
    area_ids = sorted(item["area_id"] for item in metadata["areas"])
    if not area_ids:
        raise ValueError("area artifact contains no verified Taipei areas")

    context_counts: Counter[tuple[str, str, str]] = Counter()
    context_totals: Counter[tuple[str, str]] = Counter()
    area_totals: Counter[str] = Counter()
    area_day_counts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    source_counts: Counter[tuple[str, str]] = Counter()
    known_source_counts: Counter[str] = Counter()
    origin_counts: Counter[tuple[str, str, str, str]] = Counter()
    global_counts: Counter[tuple[str, str, str]] = Counter()
    rider_visits: dict[str, Counter[int]] = defaultdict(Counter)
    train_dates: set[str] = set()
    fallback_pickup = Counter()
    fallback_dropoff = Counter()
    train_rows = 0
    eligible_rows = 0
    taipei_destination_rows = 0
    verified_destination_rows = 0

    parquet = pq.ParquetFile(input_path)
    columns = [
        "rider_id",
        "started_date",
        "period",
        "weekday_class",
        "model_eligible",
        "pickup_lat",
        "pickup_lng",
        "dropoff_lat",
        "dropoff_lng",
        "split",
    ]
    for batch in parquet.iter_batches(columns=columns, batch_size=config.batch_size):
        rows = [
            row for row in batch.to_pylist()
            if row["split"] == config.fit_split
        ]
        if not rows:
            continue
        pickup_assignments, dropoff_assignments = _assign_batch(
            area["model"],
            metadata["cluster_to_area"],
            rows,
        )
        train_rows += len(rows)
        for row, pickup, dropoff in zip(
            rows,
            pickup_assignments,
            dropoff_assignments,
        ):
            if not bool(row["model_eligible"]):
                continue
            eligible_rows += 1
            if pickup.source == "fallback":
                fallback_pickup[pickup.region] += 1
            if dropoff.source == "fallback":
                fallback_dropoff[dropoff.region] += 1
            if dropoff.region != "Taipei":
                continue
            train_dates.add(str(row["started_date"]))
            taipei_destination_rows += 1
            period = str(row["period"])
            weekday_class = str(row["weekday_class"])
            context_totals[(period, weekday_class)] += 1
            if dropoff.source != "model" or dropoff.area_id not in area_ids:
                continue
            verified_destination_rows += 1
            destination = dropoff.area_id
            context_counts[(destination, period, weekday_class)] += 1
            global_counts[(period, weekday_class, destination)] += 1
            area_totals[destination] += 1
            area_day_counts[(destination, period, weekday_class)].add(
                str(row["started_date"])
            )
            rider_visits[destination][int(row["rider_id"])] += 1
            if pickup.source == "model" and pickup.area_id in area_ids:
                source_counts[(destination, pickup.area_id)] += 1
                known_source_counts[destination] += 1
                origin_counts[
                    (pickup.area_id, period, weekday_class, destination)
                ] += 1

    raw_rows = _area_rows(
        area_ids,
        context_counts,
        context_totals,
        area_totals,
        area_day_counts,
        source_counts,
        known_source_counts,
        rider_visits,
        len(train_dates),
        config.smoothing_alpha,
    )
    scaling: dict[str, dict[str, float | bool]] = {}
    for metric in METRIC_NAMES:
        scaling[metric] = robust_scale_params(
            [float(row[f"{metric}_raw"]) for row in raw_rows]
        )
    feature_rows: list[dict[str, Any]] = []
    for row in raw_rows:
        components = {
            metric: robust_minmax(
                float(row[f"{metric}_raw"]),
                scaling[metric],
            )
            for metric in METRIC_NAMES
        }
        area_score = (
            0.30 * components["visit_heat"]
            + 0.25 * components["period_lift"]
            + 0.15 * components["cross_area_ratio"]
            + 0.15 * components["source_diversity"]
            + 0.15 * components["return_rate"]
        )
        feature_rows.append(
            {
                "area_id": row["area_id"],
                "period": row["period"],
                "weekday_class": row["weekday_class"],
                "context_key": row["context_key"],
                "area_score": round(float(area_score), 12),
                "components": {
                    key: round(float(value), 12)
                    for key, value in components.items()
                },
                "evidence": {
                    "visit_count": row["visit_count"],
                    "daily_visit_mean": round(float(row["daily_visit_mean"]), 12),
                    "days_with_visits": row["days_with_visits"],
                    "rider_count": row["rider_count"],
                    "repeat_rider_count": row["repeat_rider_count"],
                    "known_source_count": known_source_counts[row["area_id"]],
                },
            }
        )
    feature_rows.sort(
        key=lambda row: (
            row["area_id"],
            row["period"],
            row["weekday_class"],
        )
    )
    global_rankings = _ranked_counts(global_counts, include_origin=False)
    origin_rankings = _ranked_counts(origin_counts, include_origin=True)
    feature_hash = _json_digest(feature_rows)
    artifact = {
        "artifact_version": FEATURE_ARTIFACT_VERSION,
        "input_sha256": metadata["input_sha256"],
        "area_model_version": metadata["model_version"],
        "area_artifact_hash": metadata["artifact_hash"],
        "fit_split": config.fit_split,
        "policy": metadata["config"]["policy"],
        "smoothing_alpha": config.smoothing_alpha,
        "normalization": scaling,
        "weights": {
            "visit_heat": 0.30,
            "period_lift": 0.25,
            "cross_area_ratio": 0.15,
            "source_diversity": 0.15,
            "return_rate": 0.15,
        },
        "scope": "Taipei Demo only",
        "train_rows_read": train_rows,
        "eligible_train_rows": eligible_rows,
        "taipei_destination_rows": taipei_destination_rows,
        "verified_destination_rows": verified_destination_rows,
        "destination_coverage": (
            verified_destination_rows / taipei_destination_rows
            if taipei_destination_rows
            else 0.0
        ),
        "fallback_pickup_by_region": dict(sorted(fallback_pickup.items())),
        "fallback_dropoff_by_region": dict(sorted(fallback_dropoff.items())),
        "feature_hash": feature_hash,
        "features": feature_rows,
        "global_period_popularity": global_rankings.get("all", {}),
        "origin_period_popularity": origin_rankings,
    }
    _write_json(output_path, artifact)
    report_path.write_text(
        "\n".join(
            [
                "# Taipei Demo aggregate features",
                "",
                "這份 artifact 只保存區域與 aggregate statistics，不保存 RiderId、TripId 或 raw rows。",
                "",
                f"- area_model_version: {metadata['model_version']}",
                f"- fit_split: {config.fit_split}",
                f"- eligible_train_rows: {eligible_rows}",
                f"- Taipei destination rows: {taipei_destination_rows}",
                f"- verified destination rows: {verified_destination_rows}",
                f"- destination coverage: {artifact['destination_coverage']:.6f}",
                f"- feature rows: {len(feature_rows)}",
                f"- feature_hash: {feature_hash}",
                "",
                "缺少 verified area 的點保留在 coverage/fallback 統計中，不會被靜默刪除或冒充已驗證區域。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "artifact": artifact,
        "paths": {"json": output_path, "report": report_path},
    }


def load_feature_artifact(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
