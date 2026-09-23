from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from pipeline.features.areas import assign_rows, load_area_artifact
from pipeline.features.aggregate import load_feature_artifact
from pipeline.features.ranking import (
    rank_area_attraction,
    rank_origin_period,
)

EVALUATION_ARTIFACT_VERSION = "phase3-taipei-evaluation-v1"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _new_model_stats() -> dict[str, Any]:
    return {
        "rows_in_scope": 0,
        "destination_coverage_rows": 0,
        "hit5": 0,
        "mrr5_sum": 0.0,
    }


def _record(
    stats: dict[str, Any],
    ranked_ids: list[str],
    actual_area: str | None,
) -> None:
    stats["rows_in_scope"] += 1
    if actual_area is None:
        return
    stats["destination_coverage_rows"] += 1
    try:
        index = ranked_ids.index(actual_area)
    except ValueError:
        return
    if index < 5:
        stats["hit5"] += 1
        stats["mrr5_sum"] += 1.0 / (index + 1)


def _finish(stats: dict[str, Any]) -> dict[str, Any]:
    covered = stats["destination_coverage_rows"]
    rows = stats["rows_in_scope"]
    return {
        "rows_in_scope": rows,
        "destination_coverage": covered / rows if rows else 0.0,
        "evaluated_verified_destinations": covered,
        "hit_rate_at_5": stats["hit5"] / covered if covered else 0.0,
        "mrr_at_5": stats["mrr5_sum"] / covered if covered else 0.0,
    }


def evaluate_validation(
    input_path: Path,
    area_artifact_dir: Path,
    feature_path: Path,
    output_dir: Path,
    *,
    batch_size: int = 50_000,
) -> dict[str, Any]:
    input_path = input_path.resolve()
    area = load_area_artifact(area_artifact_dir)
    features = load_feature_artifact(feature_path)
    if features["input_sha256"] != _file_sha256(input_path):
        raise ValueError("evaluation input does not match the feature artifact input")
    if features["fit_split"] != "train":
        raise ValueError("evaluation requires a Train-fitted feature artifact")

    output_dir.mkdir(parents=True, exist_ok=True)
    model_stats = {
        "area_attraction_a": _new_model_stats(),
        "origin_period_popularity": _new_model_stats(),
    }
    by_period: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: {
            "area_attraction_a": _new_model_stats(),
            "origin_period_popularity": _new_model_stats(),
        }
    )
    rows_read = 0
    validation_taipei_rows = 0
    validation_verified_destination_rows = 0
    fallback_pickup_rows = 0
    fallback_destination_rows = 0
    area_ids = {
        row["area_id"] for row in features["features"]
    }
    ranking_cache: dict[tuple[str, str, str, str], list[str]] = {}

    def area_ranking(period: str, weekday: str) -> list[str]:
        key = ("a", "", period, weekday)
        if key not in ranking_cache:
            ranking_cache[key] = [
                item.area_id
                for item in rank_area_attraction(
                    features,
                    period,
                    weekday,
                    top_k=max(10, len(area_ids)),
                )
            ]
        return ranking_cache[key]

    def origin_ranking(
        origin_area: str,
        period: str,
        weekday: str,
    ) -> list[str]:
        key = ("origin", origin_area, period, weekday)
        if key not in ranking_cache:
            ranking_cache[key] = [
                item.area_id
                for item in rank_origin_period(
                    features,
                    origin_area,
                    period,
                    weekday,
                    top_k=max(10, len(area_ids)),
                )
            ]
        return ranking_cache[key]

    parquet = pq.ParquetFile(input_path)
    columns = [
        "period",
        "weekday_class",
        "pickup_lat",
        "pickup_lng",
        "dropoff_lat",
        "dropoff_lng",
        "split",
    ]
    for batch in parquet.iter_batches(columns=columns, batch_size=batch_size):
        rows = [
            row for row in batch.to_pylist()
            if row["split"] == "validation"
        ]
        if not rows:
            continue
        pickup_points = [
            (float(row["pickup_lat"]), float(row["pickup_lng"])) for row in rows
        ]
        dropoff_points = [
            (float(row["dropoff_lat"]), float(row["dropoff_lng"])) for row in rows
        ]
        pickup_assignments, dropoff_assignments = assign_rows(
            area["model"],
            pickup_points,
            dropoff_points,
            area["metadata"]["cluster_to_area"],
        )
        rows_read += len(rows)
        for row, pickup, dropoff in zip(
            rows,
            pickup_assignments,
            dropoff_assignments,
        ):
            if dropoff.region != "Taipei":
                continue
            validation_taipei_rows += 1
            actual_area = (
                dropoff.area_id
                if dropoff.source == "model" and dropoff.area_id in area_ids
                else None
            )
            if actual_area is not None:
                validation_verified_destination_rows += 1
            if pickup.source == "fallback":
                fallback_pickup_rows += 1
            if dropoff.source == "fallback":
                fallback_destination_rows += 1
            period = str(row["period"])
            weekday = str(row["weekday_class"])
            area_ids_ranked = area_ranking(period, weekday)
            origin_ids_ranked = (
                origin_ranking(pickup.area_id, period, weekday)
                if pickup.source == "model"
                else area_ids_ranked
            )
            _record(model_stats["area_attraction_a"], area_ids_ranked, actual_area)
            _record(
                model_stats["origin_period_popularity"],
                origin_ids_ranked,
                actual_area,
            )
            _record(
                by_period[period]["area_attraction_a"],
                area_ids_ranked,
                actual_area,
            )
            _record(
                by_period[period]["origin_period_popularity"],
                origin_ids_ranked,
                actual_area,
            )

    report = {
        "artifact_version": EVALUATION_ARTIFACT_VERSION,
        "input_sha256": features["input_sha256"],
        "area_model_version": area["metadata"]["model_version"],
        "feature_hash": features["feature_hash"],
        "fit_split": "train",
        "evaluation_split": "validation",
        "test_used": False,
        "scope": "Taipei Demo only",
        "rows_read_in_validation": rows_read,
        "validation_taipei_rows": validation_taipei_rows,
        "validation_verified_destination_rows": validation_verified_destination_rows,
        "validation_destination_coverage": (
            validation_verified_destination_rows / validation_taipei_rows
            if validation_taipei_rows
            else 0.0
        ),
        "fallback_pickup_rows": fallback_pickup_rows,
        "fallback_destination_rows": fallback_destination_rows,
        "models": {
            name: _finish(stats) for name, stats in model_stats.items()
        },
        "by_period": {
            period: {
                name: _finish(stats) for name, stats in values.items()
            }
            for period, values in sorted(by_period.items())
        },
        "limitations": [
            "本輪只報告 Taipei Demo scope，不宣稱全台泛化。",
            "本輪只使用 Train fit 與 Validation evidence，Test 尚未使用。",
            "B 相似乘客、C 個人移動適配度與完整六模型比較仍不在本 smoke artifact。",
            "actual destination 為 noise/fallback 的題目保留在 coverage 分母，不直接刪除。",
        ],
    }
    report_path = output_dir / "validation_report.json"
    markdown_path = output_dir / "validation_report.md"
    _write_json(report_path, report)
    markdown_path.write_text(
        "\n".join(
            [
                "# Taipei Demo validation smoke evidence",
                "",
                "這份報告只使用 Train fit 的 artifact 與 Validation rows；Test 尚未使用。",
                "",
                f"- validation rows read: {rows_read}",
                f"- Taipei rows: {validation_taipei_rows}",
                f"- verified destination coverage: {report['validation_destination_coverage']:.6f}",
                f"- fallback pickup rows: {fallback_pickup_rows}",
                f"- fallback destination rows: {fallback_destination_rows}",
                "",
                "| model | destination coverage | HitRate@5 | MRR@5 | evaluated destinations |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
            + [
                "| {name} | {coverage:.6f} | {hit:.6f} | {mrr:.6f} | {count} |".format(
                    name=name,
                    coverage=values["destination_coverage"],
                    hit=values["hit_rate_at_5"],
                    mrr=values["mrr_at_5"],
                    count=values["evaluated_verified_destinations"],
                )
                for name, values in report["models"].items()
            ]
            + [
                "",
                "## Limitations",
                "",
                *[f"- {item}" for item in report["limitations"]],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "report": report,
        "paths": {"json": report_path, "markdown": markdown_path},
    }
