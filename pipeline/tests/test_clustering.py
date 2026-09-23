from __future__ import annotations

import math

import pytest

from pipeline.clustering.geometry import (
    deterministic_stratified_sample,
    degrees_to_radians,
    haversine_km,
    points_digest,
    region_for_point,
)


def test_degrees_to_radians_uses_haversine_units() -> None:
    latitude, longitude = degrees_to_radians(180.0, 90.0)
    assert latitude == pytest.approx(math.pi)
    assert longitude == pytest.approx(math.pi / 2.0)


def test_haversine_zero_and_known_distance() -> None:
    assert haversine_km(25.0, 121.0, 25.0, 121.0) == pytest.approx(0.0)
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, rel=1e-3)


def test_region_buckets_are_deterministic() -> None:
    assert region_for_point(25.05, 121.52) == "Taipei"
    assert region_for_point(24.15, 120.67) == "Taichung"
    assert region_for_point(22.63, 120.30) == "Kaohsiung"
    assert region_for_point(21.0, 119.0) == "Other/Unknown"


def test_stratified_sample_is_deterministic_and_bounded() -> None:
    points = [
        (25.0 + index * 0.001, 121.0, "Taipei") for index in range(60)
    ] + [
        (24.0 + index * 0.001, 120.5, "Taichung") for index in range(40)
    ]
    first = deterministic_stratified_sample(points, 50)
    second = deterministic_stratified_sample(points, 50)
    assert first == second
    assert len(first) == 50
    assert {point[2] for point in first} == {"Taipei", "Taichung"}
    assert points_digest(first) == points_digest(second)


def test_stratified_sample_rejects_oversize() -> None:
    with pytest.raises(ValueError):
        deterministic_stratified_sample([(25.0, 121.0, "Taipei")], 2)
