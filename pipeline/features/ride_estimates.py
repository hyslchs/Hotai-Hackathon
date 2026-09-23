from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


ALL_PERIODS = "all_periods"
ALL_REGIONS = "all_regions"
MIN_SAMPLE_COUNT = 30


def distance_bin(distance_km: float) -> str:
    if distance_km < 2:
        return "under_2km"
    if distance_km < 5:
        return "2_to_5km"
    if distance_km < 10:
        return "5_to_10km"
    return "10km_plus"


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def build_fare_estimate_artifact(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate only model-eligible Train fare midpoints; never retain trip rows."""
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    accepted = 0
    for row in rows:
        if row.get("split") != "train" or not row.get("model_eligible"):
            continue
        midpoint = row.get("fare_midpoint")
        distance = row.get("distance_km")
        period = row.get("period")
        region = row.get("pickup_region")
        if midpoint is None or distance is None or not period or not region:
            continue
        accepted += 1
        bucket = distance_bin(float(distance))
        for context in (
            (bucket, str(period), str(region)),
            (bucket, str(period), ALL_REGIONS),
            (bucket, ALL_PERIODS, str(region)),
            (bucket, ALL_PERIODS, ALL_REGIONS),
        ):
            grouped[context].append(float(midpoint))

    estimates = []
    for (bucket, period, region), values in sorted(grouped.items()):
        if len(values) < MIN_SAMPLE_COUNT:
            continue
        estimates.append(
            {
                "distance_bin": bucket,
                "period": period,
                "region_label": region,
                "fare_p25": round(_quantile(values, 0.25), 2),
                "fare_p75": round(_quantile(values, 0.75), 2),
                "sample_count": len(values),
            }
        )
    return {
        "artifact_type": "train_fare_estimates",
        "split": "train",
        "minimum_sample_count": MIN_SAMPLE_COUNT,
        "accepted_row_count": accepted,
        "estimates": estimates,
    }
