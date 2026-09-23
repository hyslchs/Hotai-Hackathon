from __future__ import annotations

from datetime import datetime

import pytest

from pipeline.cleaning.contract import (
    ContractError,
    SOURCE_FIELDS,
    TAIPEI,
    parse_datetime,
    parse_fare_range,
    parse_source_row,
    validate_columns,
)
from pipeline.tests.fixtures.synthetic import iter_synthetic_rows


def test_synthetic_fixture_has_1000_valid_rows():
    rows = [parse_source_row(row) for row in iter_synthetic_rows(1000)]

    assert len(rows) == 1000
    assert all(row.started_at.tzinfo is not None for row in rows)
    assert all(row.started_at.tzinfo == TAIPEI for row in rows)
    assert all(row.fare.midpoint >= row.fare.lower_exclusive for row in rows)


def test_source_columns_are_exact_and_ordered():
    validate_columns(SOURCE_FIELDS)
    with pytest.raises(ContractError):
        validate_columns((*SOURCE_FIELDS[:-1], "Unexpected"))


def test_fare_is_lower_exclusive_and_upper_inclusive():
    fare = parse_fare_range("[100,200]")

    assert fare.lower_exclusive == 101
    assert fare.upper_inclusive == 200
    assert fare.midpoint == 150.5


def test_datetime_normalizes_to_asia_taipei():
    aware = parse_datetime("2026-02-01T08:00:00+00:00", "started_at")
    naive = parse_datetime("2026-02-01 08:00:00.000", "started_at")

    assert aware.utcoffset().total_seconds() == 8 * 60 * 60
    assert aware.hour == 16
    assert naive.tzinfo == TAIPEI


def test_nullable_poi_and_invalid_fare_are_explicit():
    row = next(iter_synthetic_rows(1))
    row["PickUpLocationType"] = " "
    parsed = parse_source_row(row)
    assert parsed.pickup_poi_text is None

    with pytest.raises(ContractError):
        parse_fare_range("unknown")


def test_negative_measure_is_rejected():
    row = next(iter_synthetic_rows(1))
    row["TravelDistance"] = "-1"

    with pytest.raises(ContractError):
        parse_source_row(row)

