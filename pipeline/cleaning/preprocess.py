from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from .contract import ContractError, SOURCE_FIELDS, TAIPEI, TripRecord, parse_source_row

TRAIN_CUTOFF = datetime(2026, 3, 16, tzinfo=TAIPEI)
VALIDATION_CUTOFF = datetime(2026, 4, 1, tzinfo=TAIPEI)
HARD_RULE_ORDER = (
    "column_count",
    "required_field_parse",
    "datetime_parse",
    "fare_parse",
    "coordinate_parse",
    "travel_time_parse",
    "travel_distance_parse",
    "duplicate_trip_id",
    "ended_before_started",
    "ordered_after_started",
    "coordinate_out_of_range",
    "travel_time_nonpositive",
    "travel_distance_negative",
)
SOFT_RULE_ORDER = (
    "distance_zero",
    "speed_low",
    "speed_high",
    "travel_time_long",
    "distance_long",
    "elapsed_time_mismatch",
)

CLEAN_SCHEMA = pa.schema(
    [
        ("trip_id", pa.int64()),
        ("rider_id", pa.int64()),
        ("started_at", pa.timestamp("us", tz="Asia/Taipei")),
        ("ended_at", pa.timestamp("us", tz="Asia/Taipei")),
        ("pickup_lat", pa.float64()),
        ("pickup_lng", pa.float64()),
        ("dropoff_lat", pa.float64()),
        ("dropoff_lng", pa.float64()),
        ("travel_time_min", pa.int64()),
        ("travel_distance_m", pa.int64()),
        ("ordered_at", pa.timestamp("us", tz="Asia/Taipei")),
        ("pickup_poi_text", pa.string()),
        ("dropoff_poi_text", pa.string()),
        ("fare_raw", pa.string()),
        ("fare_lower_exclusive", pa.float64()),
        ("fare_upper_inclusive", pa.float64()),
        ("fare_midpoint", pa.float64()),
        ("weekday_class", pa.string()),
        ("period", pa.string()),
        ("distance_km", pa.float64()),
        ("elapsed_time_min", pa.float64()),
        ("speed_kph", pa.float64()),
        ("model_eligible", pa.bool_()),
        ("exclusion_reasons", pa.string()),
        ("split", pa.string()),
        ("pickup_region", pa.string()),
        ("started_date", pa.string()),
    ]
)

QUARANTINE_SCHEMA = pa.schema(
    [(field, pa.string()) for field in SOURCE_FIELDS]
    + [
        ("row_number", pa.int64()),
        ("quarantine_reasons", pa.string()),
    ]
)


@dataclass(frozen=True)
class CleaningConfig:
    pipeline_version: str = "phase1-cleaning-v1"
    chunk_size: int = 50_000
    latitude_min: float = 20.0
    latitude_max: float = 27.0
    longitude_min: float = 118.0
    longitude_max: float = 123.0
    max_travel_time_min: int = 180
    max_travel_distance_m: int = 200_000
    min_speed_kph: float = 1.0
    max_speed_kph: float = 120.0
    elapsed_time_tolerance_min: float = 2.0
    seed: int | None = None


def load_dotenv_values(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    path = root / ".env"
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def choose_input(root: Path, configured: str | None = None) -> Path:
    dotenv = load_dotenv_values(root)
    configured_value = configured or os.getenv("RAW_DATA_PATH") or dotenv.get("RAW_DATA_PATH")
    candidates: list[Path] = []
    if configured_value:
        candidates.append(Path(configured_value))
    candidates.extend(
        [
            Path("data/raw/yoxi_數據資料.csv"),
            Path("data/yoxi_rawdata.csv"),
        ]
    )
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else root / candidate
        if resolved.is_file():
            return resolved.resolve()
    names = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"no raw CSV found in configured candidates: {names}")


def choose_output_dir(root: Path, name: str, configured: str | None = None) -> Path:
    dotenv = load_dotenv_values(root)
    configured_value = configured or os.getenv(name) or dotenv.get(name)
    value = configured_value or ("data/processed" if name == "PROCESSED_DATA_DIR" else "data/reports")
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def update_content_digest(digest: "hashlib._Hash", value: Mapping[str, object]) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    digest.update(payload)
    digest.update(b"\n")


def split_for(started_at: datetime) -> str:
    normalized = started_at.astimezone(TAIPEI)
    if normalized < TRAIN_CUTOFF:
        return "train"
    if normalized < VALIDATION_CUTOFF:
        return "validation"
    return "test"


def period_for(started_at: datetime) -> str:
    hour = started_at.astimezone(TAIPEI).hour
    if 5 <= hour <= 10:
        return "morning"
    if 11 <= hour <= 13:
        return "lunch"
    if 14 <= hour <= 16:
        return "afternoon"
    if 17 <= hour <= 20:
        return "dinner"
    return "night"


def region_bucket(latitude: float, longitude: float) -> str:
    if 24.7 <= latitude <= 25.4 and 121.2 <= longitude <= 122.0:
        return "Taipei"
    if 23.8 <= latitude < 24.7 and 120.2 <= longitude < 121.4:
        return "Taichung"
    if 22.4 <= latitude < 23.8 and 120.0 <= longitude < 121.2:
        return "Kaohsiung"
    return "Other/Unknown"


def contract_error_rule(error: ContractError) -> str:
    message = str(error).lower()
    if "paymenttotalrange" in message:
        return "fare_parse"
    if "travel_time" in message or "traveltime" in message:
        return "travel_time_parse"
    if "travel_distance" in message or "traveldistance" in message:
        return "travel_distance_parse"
    if "latitude" in message or "longitude" in message:
        return "coordinate_parse"
    if "date" in message or "time" in message:
        return "datetime_parse"
    return "required_field_parse"


def unique_in_order(reasons: Iterable[str], order: Sequence[str]) -> list[str]:
    found = set(reasons)
    return [item for item in order if item in found]


def hard_reasons_for(
    record: TripRecord,
    candidate_duplicate: bool,
    config: CleaningConfig,
) -> list[str]:
    reasons: list[str] = []
    if candidate_duplicate:
        reasons.append("duplicate_trip_id")
    if record.ended_at < record.started_at:
        reasons.append("ended_before_started")
    if record.ordered_at > record.started_at:
        reasons.append("ordered_after_started")
    coordinates = (
        record.pickup_lat,
        record.pickup_lng,
        record.dropoff_lat,
        record.dropoff_lng,
    )
    if not all(math.isfinite(value) for value in coordinates):
        reasons.append("coordinate_parse")
    elif not (
        config.latitude_min <= record.pickup_lat <= config.latitude_max
        and config.latitude_min <= record.dropoff_lat <= config.latitude_max
        and config.longitude_min <= record.pickup_lng <= config.longitude_max
        and config.longitude_min <= record.dropoff_lng <= config.longitude_max
    ):
        reasons.append("coordinate_out_of_range")
    if record.travel_time_min <= 0:
        reasons.append("travel_time_nonpositive")
    if record.travel_distance_m < 0:
        reasons.append("travel_distance_negative")
    return unique_in_order(reasons, HARD_RULE_ORDER)


def soft_reasons_for(
    record: TripRecord,
    config: CleaningConfig,
) -> tuple[list[str], float, float, float]:
    distance_km = record.travel_distance_m / 1000.0
    elapsed_time_min = (record.ended_at - record.started_at).total_seconds() / 60.0
    speed_kph = (
        distance_km / (record.travel_time_min / 60.0)
        if record.travel_time_min > 0
        else math.nan
    )
    reasons: list[str] = []
    if record.travel_distance_m == 0:
        reasons.append("distance_zero")
    if math.isfinite(speed_kph) and speed_kph < config.min_speed_kph:
        reasons.append("speed_low")
    if math.isfinite(speed_kph) and speed_kph > config.max_speed_kph:
        reasons.append("speed_high")
    if record.travel_time_min > config.max_travel_time_min:
        reasons.append("travel_time_long")
    if record.travel_distance_m > config.max_travel_distance_m:
        reasons.append("distance_long")
    if abs(elapsed_time_min - record.travel_time_min) > config.elapsed_time_tolerance_min:
        reasons.append("elapsed_time_mismatch")
    return unique_in_order(reasons, SOFT_RULE_ORDER), distance_km, elapsed_time_min, speed_kph


def clean_row_from_record(
    record: TripRecord,
    config: CleaningConfig,
) -> tuple[dict[str, object], list[str]]:
    soft_reasons, distance_km, elapsed_time_min, speed_kph = soft_reasons_for(record, config)
    started_at = record.started_at.astimezone(TAIPEI)
    row = {
        "trip_id": record.trip_id,
        "rider_id": record.rider_id,
        "started_at": started_at,
        "ended_at": record.ended_at.astimezone(TAIPEI),
        "pickup_lat": record.pickup_lat,
        "pickup_lng": record.pickup_lng,
        "dropoff_lat": record.dropoff_lat,
        "dropoff_lng": record.dropoff_lng,
        "travel_time_min": record.travel_time_min,
        "travel_distance_m": record.travel_distance_m,
        "ordered_at": record.ordered_at.astimezone(TAIPEI),
        "pickup_poi_text": record.pickup_poi_text,
        "dropoff_poi_text": record.dropoff_poi_text,
        "fare_raw": record.fare.raw,
        "fare_lower_exclusive": float(record.fare.lower_exclusive),
        "fare_upper_inclusive": float(record.fare.upper_inclusive),
        "fare_midpoint": float(record.fare.midpoint),
        "weekday_class": "weekday" if started_at.weekday() < 5 else "weekend",
        "period": period_for(started_at),
        "distance_km": distance_km,
        "elapsed_time_min": elapsed_time_min,
        "speed_kph": speed_kph,
        "model_eligible": not soft_reasons,
        "exclusion_reasons": ";".join(soft_reasons),
        "split": split_for(started_at),
        "pickup_region": region_bucket(record.pickup_lat, record.pickup_lng),
        "started_date": started_at.date().isoformat(),
    }
    return row, soft_reasons


def quarantine_row(
    values: Sequence[str],
    row_number: int,
    reasons: Sequence[str],
) -> dict[str, object]:
    padded = list(values[: len(SOURCE_FIELDS)])
    padded.extend([None] * (len(SOURCE_FIELDS) - len(padded)))
    row: dict[str, object] = {
        field: value for field, value in zip(SOURCE_FIELDS, padded)
    }
    row["row_number"] = row_number
    row["quarantine_reasons"] = ";".join(
        unique_in_order(reasons, HARD_RULE_ORDER)
    )
    return row


def write_rows(
    writer: pq.ParquetWriter,
    rows: list[dict[str, object]],
    schema: pa.Schema,
) -> None:
    if not rows:
        return
    writer.write_table(pa.Table.from_pylist(rows, schema=schema))
    rows.clear()


def nested_counter(counter: Mapping[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        key: {rule: int(counts[rule]) for rule in sorted(counts)}
        for key, counts in sorted(counter.items())
    }


def markdown_report(report: Mapping[str, object]) -> str:
    counts = report["counts"]
    split_counts = report["split_counts"]
    hard = report["hard_invalid"]
    soft = report["soft_outliers"]
    lines = [
        "# Phase 1 quality report",
        "",
        "這份報告只呈現 aggregate counts，不包含 raw row、RiderId 或 POI 原文。",
        "",
        "## Reconciliation",
        "",
        f"- Input logical rows: {counts['input_rows']}",
        f"- Clean rows: {counts['clean_rows']}",
        f"- Quarantine rows: {counts['quarantine_rows']}",
        f"- Reconciled: {counts['reconciled']}",
        "",
        "## Split counts before model exclusions",
        "",
        "| split | rows |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {name} | {split_counts.get(name, 0)} |"
        for name in ("train", "validation", "test")
    )
    lines.extend(
        [
            "",
            f"- May 1 after-midnight rows in Test: {report['boundary_counts']['may1_after_midnight_test_rows']}",
            "",
            "## Hard-invalid rules",
            "",
            "| rule | rows |",
            "| --- | ---: |",
        ]
    )
    lines.extend(
        f"| {name} | {value} |"
        for name, value in hard["by_rule"].items()
    )
    lines.extend(
        [
            "",
            "## Soft-outlier rules",
            "",
            f"Rows with at least one soft rule: {soft['union_rows']}",
            "",
            "| rule | rows |",
            "| --- | ---: |",
        ]
    )
    lines.extend(
        f"| {name} | {value} |"
        for name, value in soft["by_rule"].items()
    )
    lines.extend(
        [
            "",
            "## Soft-outlier audit buckets",
            "",
            "Region buckets are deterministic coordinate audit buckets, not official geocoding or clustering.",
            "",
            "### By region",
            "",
        ]
    )
    for region, values in soft["by_region"].items():
        lines.append(f"- {region}: {values}")
    lines.extend(
        [
            "",
            "### By started date",
            "",
        ]
    )
    for date, values in soft["by_started_date"].items():
        lines.append(f"- {date}: {values}")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Soft-outlier thresholds are initial rules from PROJECT_SPEC.md and require later review.",
            "- This phase does not claim model quality and does not fit any model or scaler.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_pipeline(
    input_path: Path,
    processed_dir: Path,
    reports_dir: Path,
    config: CleaningConfig | None = None,
) -> dict[str, object]:
    config = config or CleaningConfig()
    input_path = input_path.resolve()
    processed_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    clean_path = processed_dir / "trips_clean.parquet"
    quarantine_path = processed_dir / "trips_quarantine.parquet"
    report_json_path = reports_dir / "quality_report.json"
    report_md_path = reports_dir / "quality_report.md"
    manifest_path = reports_dir / "run_manifest.json"

    input_sha = sha256_file(input_path)
    clean_content_digest = hashlib.sha256()
    quarantine_content_digest = hashlib.sha256()
    raw_rows = 0
    clean_rows = 0
    quarantine_rows = 0
    seen_trip_ids: set[int] = set()
    hard_counts: Counter[str] = Counter()
    soft_counts: Counter[str] = Counter()
    soft_by_region: defaultdict[str, Counter[str]] = defaultdict(Counter)
    soft_by_date: defaultdict[str, Counter[str]] = defaultdict(Counter)
    split_counts: Counter[str] = Counter()
    model_eligible_counts: Counter[str] = Counter()
    boundary_counts: Counter[str] = Counter()
    clean_buffer: list[dict[str, object]] = []
    quarantine_buffer: list[dict[str, object]] = []

    clean_writer = pq.ParquetWriter(clean_path, CLEAN_SCHEMA, compression="zstd")
    quarantine_writer = pq.ParquetWriter(
        quarantine_path,
        QUARANTINE_SCHEMA,
        compression="zstd",
    )
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header != list(SOURCE_FIELDS):
                raise ValueError("source header does not match the 14-field contract")

            for row_number, values in enumerate(reader, start=2):
                if not values or all(not value.strip() for value in values):
                    continue
                raw_rows += 1
                reasons: list[str] = []
                candidate_id: int | None = None
                if len(values) == len(SOURCE_FIELDS):
                    try:
                        candidate_id = int(values[0].strip())
                    except (TypeError, ValueError):
                        candidate_id = None
                if candidate_id is not None:
                    if candidate_id in seen_trip_ids:
                        reasons.append("duplicate_trip_id")
                    else:
                        seen_trip_ids.add(candidate_id)

                record: TripRecord | None = None
                if len(values) != len(SOURCE_FIELDS):
                    reasons.append("column_count")
                else:
                    raw_mapping = dict(zip(SOURCE_FIELDS, values))
                    try:
                        record = parse_source_row(raw_mapping)
                    except ContractError as error:
                        reasons.append(contract_error_rule(error))

                if record is not None:
                    reasons.extend(
                        hard_reasons_for(record, "duplicate_trip_id" in reasons, config)
                    )

                ordered_hard_reasons = unique_in_order(reasons, HARD_RULE_ORDER)
                if ordered_hard_reasons:
                    quarantine_rows += 1
                    hard_counts.update(ordered_hard_reasons)
                    qrow = quarantine_row(values, row_number, ordered_hard_reasons)
                    quarantine_buffer.append(qrow)
                    update_content_digest(
                        quarantine_content_digest,
                        {key: qrow.get(key) for key in (*SOURCE_FIELDS, "quarantine_reasons")},
                    )
                else:
                    assert record is not None
                    clean_row, soft_reasons = clean_row_from_record(record, config)
                    clean_rows += 1
                    split_counts[str(clean_row["split"])] += 1
                    if (
                        clean_row["started_date"] == "2026-05-01"
                        and clean_row["started_at"].hour < 1
                    ):
                        boundary_counts["may1_after_midnight_test_rows"] += 1
                    if bool(clean_row["model_eligible"]):
                        model_eligible_counts[str(clean_row["split"])] += 1
                    soft_counts.update(soft_reasons)
                    if soft_reasons:
                        region = str(clean_row["pickup_region"])
                        date = str(clean_row["started_date"])
                        soft_by_region[region].update(soft_reasons)
                        soft_by_date[date].update(soft_reasons)
                    update_content_digest(clean_content_digest, clean_row)
                    clean_buffer.append(clean_row)

                if len(clean_buffer) >= config.chunk_size:
                    write_rows(clean_writer, clean_buffer, CLEAN_SCHEMA)
                if len(quarantine_buffer) >= config.chunk_size:
                    write_rows(quarantine_writer, quarantine_buffer, QUARANTINE_SCHEMA)

        write_rows(clean_writer, clean_buffer, CLEAN_SCHEMA)
        write_rows(quarantine_writer, quarantine_buffer, QUARANTINE_SCHEMA)
    finally:
        clean_writer.close()
        quarantine_writer.close()

    report: dict[str, object] = {
        "report_version": "phase1-quality-v1",
        "input": {
            "path": input_path.name,
            "size_bytes": input_path.stat().st_size,
            "sha256": input_sha,
        },
        "config": asdict(config),
        "counts": {
            "input_rows": raw_rows,
            "clean_rows": clean_rows,
            "quarantine_rows": quarantine_rows,
            "reconciled": clean_rows + quarantine_rows == raw_rows,
        },
        "split_counts": {
            name: int(split_counts.get(name, 0))
            for name in ("train", "validation", "test")
        },
        "model_eligible_counts": {
            name: int(model_eligible_counts.get(name, 0))
            for name in ("train", "validation", "test")
        },
        "boundary_counts": {
            "may1_after_midnight_test_rows": int(
                boundary_counts["may1_after_midnight_test_rows"]
            )
        },
        "hard_invalid": {
            "quarantine_rows": quarantine_rows,
            "by_rule": {
                name: int(hard_counts.get(name, 0))
                for name in HARD_RULE_ORDER
                if hard_counts.get(name, 0)
            },
        },
        "soft_outliers": {
            "union_rows": 0,
            "by_rule": {
                name: int(soft_counts.get(name, 0))
                for name in SOFT_RULE_ORDER
                if soft_counts.get(name, 0)
            },
            "by_region": nested_counter(soft_by_region),
            "by_started_date": nested_counter(soft_by_date),
        },
    }
    # Count the soft union from model eligibility and clean row counts without
    # retaining row-level state.
    eligible_total = sum(model_eligible_counts.values())
    report["soft_outliers"]["union_rows"] = clean_rows - eligible_total

    report_json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(markdown_report(report), encoding="utf-8")

    artifacts = {
        "trips_clean.parquet": {
            "path": "data/processed/trips_clean.parquet",
            "sha256": sha256_file(clean_path),
            "content_sha256": clean_content_digest.hexdigest(),
        },
        "trips_quarantine.parquet": {
            "path": "data/processed/trips_quarantine.parquet",
            "sha256": sha256_file(quarantine_path),
            "content_sha256": quarantine_content_digest.hexdigest(),
        },
        "quality_report.json": {
            "path": "data/reports/quality_report.json",
            "sha256": sha256_file(report_json_path),
        },
        "quality_report.md": {
            "path": "data/reports/quality_report.md",
            "sha256": sha256_file(report_md_path),
        },
    }
    manifest = {
        "manifest_version": "phase1-manifest-v1",
        "pipeline_version": config.pipeline_version,
        "input_sha256": input_sha,
        "config": asdict(config),
        "counts": report["counts"],
        "split_counts": report["split_counts"],
        "artifacts": artifacts,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "report": report,
        "manifest": manifest,
        "paths": {
            "clean": clean_path,
            "quarantine": quarantine_path,
            "quality_json": report_json_path,
            "quality_markdown": report_md_path,
            "manifest": manifest_path,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run Phase 1 cleaning and quality pipeline")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--processed-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--chunk-size", type=int, default=CleaningConfig.chunk_size)
    args = parser.parse_args(argv)

    input_path = choose_input(root, str(args.input) if args.input else None)
    processed_dir = (
        args.processed_dir.resolve()
        if args.processed_dir
        else choose_output_dir(root, "PROCESSED_DATA_DIR")
    )
    reports_dir = (
        args.reports_dir.resolve()
        if args.reports_dir
        else choose_output_dir(root, "REPORTS_DIR")
    )
    config = CleaningConfig(chunk_size=args.chunk_size)
    result = run_pipeline(input_path, processed_dir, reports_dir, config)
    report = result["report"]
    counts = report["counts"]
    print(
        "phase1_complete "
        f"input={counts['input_rows']} clean={counts['clean_rows']} "
        f"quarantine={counts['quarantine_rows']} reconciled={counts['reconciled']}"
    )
    print(f"split_counts={report['split_counts']}")
    print(f"soft_outlier_union={report['soft_outliers']['union_rows']}")
    print(f"quality_report={result['paths']['quality_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
