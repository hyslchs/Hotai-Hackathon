from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from pipeline.cleaning.contract import SOURCE_FIELDS, TAIPEI, parse_source_row
from pipeline.cleaning.preprocess import (
    CleaningConfig,
    hard_reasons_for,
    period_for,
    region_bucket,
    run_pipeline,
    soft_reasons_for,
    split_for,
)
from pipeline.tests.fixtures.synthetic import iter_synthetic_rows


def sample_record():
    return parse_source_row(next(iter_synthetic_rows(1)))


def test_period_and_split_boundaries_are_time_aware():
    assert period_for(datetime(2026, 2, 1, 5, tzinfo=TAIPEI)) == "morning"
    assert period_for(datetime(2026, 2, 1, 11, tzinfo=TAIPEI)) == "lunch"
    assert period_for(datetime(2026, 2, 1, 21, tzinfo=TAIPEI)) == "night"
    assert split_for(datetime(2026, 3, 15, 23, 59, tzinfo=TAIPEI)) == "train"
    assert split_for(datetime(2026, 3, 16, tzinfo=TAIPEI)) == "validation"
    assert split_for(datetime(2026, 4, 1, tzinfo=TAIPEI)) == "test"


def test_hard_and_soft_rules_are_independent_and_ordered():
    record = sample_record()
    invalid_coordinate = replace(record, pickup_lat=28.0)
    assert hard_reasons_for(invalid_coordinate, False, CleaningConfig()) == [
        "coordinate_out_of_range"
    ]

    soft_record = replace(record, travel_distance_m=0, travel_time_min=1)
    reasons, distance_km, elapsed_time_min, speed_kph = soft_reasons_for(
        soft_record, CleaningConfig()
    )
    assert reasons == ["distance_zero", "speed_low", "elapsed_time_mismatch"]
    assert distance_km == 0
    assert elapsed_time_min > 1
    assert speed_kph == 0


def test_region_buckets_are_explicit_audit_labels():
    assert region_bucket(25.05, 121.55) == "Taipei"
    assert region_bucket(24.15, 120.67) == "Taichung"
    assert region_bucket(22.63, 120.30) == "Kaohsiung"
    assert region_bucket(26.0, 123.0) == "Other/Unknown"


def test_small_run_reconciles_clean_and_quarantine():
    rows = list(iter_synthetic_rows(3))
    rows[1]["PickUpLatitude"] = "28.0"
    rows[2]["Id"] = rows[0]["Id"]
    test_root = Path("data/processed") / f".phase1-test-{os.getpid()}"
    shutil.rmtree(test_root, ignore_errors=True)
    test_root.mkdir(parents=True)
    try:
        source = test_root / "input.csv"
        with source.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SOURCE_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        result = run_pipeline(
            source,
            test_root / "processed",
            test_root / "reports",
            CleaningConfig(chunk_size=2),
        )
        report = result["report"]
        assert report["counts"] == {
            "input_rows": 3,
            "clean_rows": 1,
            "quarantine_rows": 2,
            "reconciled": True,
        }
        assert report["hard_invalid"]["by_rule"]["coordinate_out_of_range"] == 1
        assert report["hard_invalid"]["by_rule"]["duplicate_trip_id"] == 1
        assert report["split_counts"]["train"] == 1
        saved = json.loads((test_root / "reports" / "quality_report.json").read_text())
        assert saved["counts"] == report["counts"]
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
