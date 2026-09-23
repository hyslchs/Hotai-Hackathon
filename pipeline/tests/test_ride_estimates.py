from __future__ import annotations

from pipeline.features.ride_estimates import ALL_PERIODS, ALL_REGIONS, build_fare_estimate_artifact, distance_bin


def test_distance_bins_have_stable_boundaries():
    assert distance_bin(0.0) == "under_2km"
    assert distance_bin(1.999) == "under_2km"
    assert distance_bin(2.0) == "2_to_5km"
    assert distance_bin(5.0) == "5_to_10km"
    assert distance_bin(10.0) == "10km_plus"


def test_fare_artifact_uses_train_eligible_rows_and_has_coarse_fallbacks():
    rows = [
        {
            "split": "train", "model_eligible": True, "fare_midpoint": float(index),
            "distance_km": 3.0, "period": "dinner", "pickup_region": "Taipei",
        }
        for index in range(100, 131)
    ]
    rows.extend([
        {"split": "validation", "model_eligible": True, "fare_midpoint": 9999.0, "distance_km": 3.0, "period": "dinner", "pickup_region": "Taipei"},
        {"split": "train", "model_eligible": False, "fare_midpoint": 9999.0, "distance_km": 3.0, "period": "dinner", "pickup_region": "Taipei"},
    ])

    artifact = build_fare_estimate_artifact(rows)

    assert artifact["accepted_row_count"] == 31
    exact = next(item for item in artifact["estimates"] if item["period"] == "dinner" and item["region_label"] == "Taipei")
    assert exact["fare_p25"] == 107.5
    assert exact["fare_p75"] == 122.5
    assert any(item["period"] == ALL_PERIODS and item["region_label"] == ALL_REGIONS for item in artifact["estimates"])
