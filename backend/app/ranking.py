from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .models import Area, AreaPeriodStat, RiderAreaStat, RiderProfile


AREA_DISTANCE_KM = 20.0
AREA_EXPANDED_DISTANCE_KM = 30.0
AREA_TOP_K = 10
DEFAULT_COLD_DISTANCE_BUDGET_KM = 8.0
MIN_PROFILE_DISTANCE_BUDGET_KM = 6.0
MAX_PROFILE_DISTANCE_BUDGET_KM = 10.0
SERVING_PROXIMITY_WEIGHT = 0.20


@dataclass(frozen=True)
class RankedArea:
    area_id: str
    latitude: float
    longitude: float
    radius_km: float
    distance_km: float
    area_attraction: float
    personal_mobility: float | None
    base_model_score: float
    proximity_fit: float | None
    score: float

    def as_dict(self, rank: int) -> dict[str, object]:
        return {
            "rank": rank,
            "area_id": self.area_id,
            "centroid": {"latitude": self.latitude, "longitude": self.longitude},
            "radius_km": self.radius_km,
            "distance_km": self.distance_km,
            "score": self.score,
            "score_breakdown": {
                "area_attraction": self.area_attraction,
                "personal_mobility": self.personal_mobility,
                "base_model_score": self.base_model_score,
                "proximity_fit": self.proximity_fit,
            },
        }


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a_lat, a_lng, b_lat, b_lng))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def road_distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    return haversine_km(a_lat, a_lng, b_lat, b_lng) * 1.30


def serving_distance_budget_km(profile: RiderProfile | None) -> float:
    """Return a bounded serving preference, without changing offline evaluation.

    Cold users have no personal distance evidence, so use a conservative Taipei
    default.  For supported personas, the budget follows their aggregate median
    distance but remains bounded so one small profile cannot create an extreme
    request-time radius.
    """
    if profile is None or profile.personalization_level == "cold":
        return DEFAULT_COLD_DISTANCE_BUDGET_KM
    median = float(profile.median_distance_km or 0.0)
    if median <= 0:
        return DEFAULT_COLD_DISTANCE_BUDGET_KM
    return round(
        min(
            MAX_PROFILE_DISTANCE_BUDGET_KM,
            max(MIN_PROFILE_DISTANCE_BUDGET_KM, 1.5 * median),
        ),
        3,
    )


def proximity_fit(distance_km: float, distance_budget_km: float) -> float:
    """Score practical proximity for an already eligible area.

    The first three kilometres are treated as equally convenient.  The score
    then declines smoothly toward a small residual at the serving budget; the
    hard budget itself is enforced separately by ``rank_areas``.
    """
    if distance_km <= 3.0:
        return 1.0
    if distance_budget_km <= 3.0:
        return 0.15
    if distance_km >= distance_budget_km:
        return 0.15
    return round(
        max(
            0.15,
            0.85 - 0.70 * (distance_km - 3.0) / (distance_budget_km - 3.0),
        ),
        6,
    )


def _period_ratio(profile: RiderProfile, period: str) -> float:
    value = getattr(profile, f"{period}_ratio", None)
    return float(value) if value is not None else 0.0


def _distance_fit(distance_km: float, profile: RiderProfile, cohort_reference: dict[str, object]) -> float:
    median = float(profile.median_distance_km or 0.0)
    if median <= 0:
        return 0.0
    if profile.personalization_level == "full" and profile.p25_distance_km and profile.p75_distance_km and profile.p90_distance_km:
        p25, p75, p90 = float(profile.p25_distance_km), float(profile.p75_distance_km), float(profile.p90_distance_km)
    else:
        reference = cohort_reference.get("light", {}) if isinstance(cohort_reference, dict) else {}
        p25 = min(median, float(reference.get("p25", median)))
        p75 = max(median, float(reference.get("p75", median)))
        p90 = max(p75 + 0.1, float(reference.get("p90", p75 + 0.1)))
    if distance_km < p25:
        return max(0.0, min(1.0, 0.35 + 0.65 * distance_km / max(p25, 0.01)))
    if distance_km <= p75:
        return 1.0
    if distance_km <= p90:
        return max(0.0, 1.0 - 0.35 * (distance_km - p75) / max(p90 - p75, 0.01))
    return max(0.0, min(1.0, 0.65 * math.exp(-(distance_km - p90) / max(p90, 0.01))))


def personal_mobility_score(
    *,
    profile: RiderProfile | None,
    area_id: str,
    distance_km: float,
    period: str,
    weekday_class: str,
    area_visit_counts: dict[str, int],
    cohort_reference: dict[str, object],
) -> float | None:
    if profile is None or profile.personalization_level == "cold":
        return None
    trip_count = max(int(profile.trip_count), 0)
    distance_fit = _distance_fit(distance_km, profile, cohort_reference)
    time_habit = (_period_ratio(profile, period) * trip_count + 1.0) / (trip_count + 5.0)
    weekend_ratio = float(profile.weekend_ratio or 0.0)
    weekday_ratio = weekend_ratio if weekday_class == "weekend" else 1.0 - weekend_ratio
    weekday_fit = (weekday_ratio * trip_count + 1.0) / (trip_count + 2.0)
    maximum = max(area_visit_counts.values(), default=0)
    affinity = math.log1p(area_visit_counts.get(area_id, 0)) / math.log1p(maximum) if maximum else 0.0
    return round(max(0.0, min(1.0, 0.50 * distance_fit + 0.20 * time_habit + 0.15 * weekday_fit + 0.15 * affinity)), 6)


def rank_areas(
    *,
    origin_latitude: float,
    origin_longitude: float,
    areas: Iterable[Area],
    stats: Iterable[AreaPeriodStat],
    profile: RiderProfile | None,
    rider_area_stats: Iterable[RiderAreaStat],
    period: str,
    weekday_class: str,
    cohort_reference: dict[str, object],
    weights: dict[str, object],
    distance_budget_km: float | None = None,
    proximity_weight: float = 0.0,
) -> list[RankedArea]:
    by_area = {area.area_id: area for area in areas}
    attraction = {row.area_id: float(row.attraction_score) for row in stats if row.area_id in by_area}
    distances = {
        area_id: road_distance_km(origin_latitude, origin_longitude, area.centroid_lat, area.centroid_lng)
        for area_id, area in by_area.items()
        if area_id in attraction
    }
    if distance_budget_km is None:
        eligible = [area_id for area_id, distance in distances.items() if distance <= AREA_DISTANCE_KM]
        if len(eligible) < AREA_TOP_K:
            eligible = [area_id for area_id, distance in distances.items() if distance <= AREA_EXPANDED_DISTANCE_KM]
    else:
        eligible = [area_id for area_id, distance in distances.items() if distance <= distance_budget_km]
    visit_counts = {row.area_id: int(row.visit_count) for row in rider_area_stats if row.period == period}
    a_weight = float(weights.get("a", 0.30))
    c_weight = float(weights.get("c", 0.70))
    result: list[RankedArea] = []
    for area_id in eligible:
        area = by_area[area_id]
        distance = distances[area_id]
        c_score = personal_mobility_score(
            profile=profile,
            area_id=area_id,
            distance_km=distance,
            period=period,
            weekday_class=weekday_class,
            area_visit_counts=visit_counts,
            cohort_reference=cohort_reference,
        )
        base_score = attraction[area_id] if c_score is None else a_weight * attraction[area_id] + c_weight * c_score
        area_proximity = None if distance_budget_km is None else proximity_fit(distance, distance_budget_km)
        if area_proximity is None or proximity_weight <= 0:
            score = base_score
        else:
            bounded_weight = min(max(float(proximity_weight), 0.0), 1.0)
            score = (1.0 - bounded_weight) * base_score + bounded_weight * area_proximity
        result.append(RankedArea(
            area_id=area_id,
            latitude=area.centroid_lat,
            longitude=area.centroid_lng,
            radius_km=area.radius_p90_km,
            distance_km=round(distance, 4),
            area_attraction=round(attraction[area_id], 6),
            personal_mobility=c_score,
            base_model_score=round(base_score, 6),
            proximity_fit=area_proximity,
            score=round(score, 6),
        ))
    return sorted(result, key=lambda item: (-item.score, item.area_id))[:AREA_TOP_K]


def contextual_fit(*, route_minutes: int, route_distance_km: float, profile: RiderProfile | None, cohort_reference: dict[str, object]) -> tuple[float, dict[str, float]]:
    """Score whether a restaurant trip is practical, without changing area A+C.

    This is a separate restaurant layer: the accepted offline model ranks areas;
    route time and distance decide how suitable a specific restaurant is inside
    those areas.  Values are intentionally bounded and deterministic.
    """
    typical_minutes = float(profile.median_duration_min) if profile and profile.median_duration_min else 20.0
    if route_minutes <= typical_minutes:
        travel_time_fit = 1.0
    elif route_minutes <= typical_minutes * 1.5:
        travel_time_fit = 1.0 - 0.35 * (route_minutes - typical_minutes) / max(typical_minutes * 0.5, 1.0)
    else:
        travel_time_fit = 0.65 * math.exp(-(route_minutes - typical_minutes * 1.5) / max(typical_minutes, 1.0))

    preferred_distance = 10.0
    if profile and profile.p90_distance_km:
        preferred_distance = float(profile.p90_distance_km)
    elif isinstance(cohort_reference, dict):
        light = cohort_reference.get("light", {})
        if isinstance(light, dict):
            preferred_distance = float(light.get("p90", preferred_distance))
    if route_distance_km < 1.0:
        ride_worthiness = 0.10 + 0.45 * route_distance_km
    elif route_distance_km <= min(10.0, preferred_distance):
        ride_worthiness = 1.0
    else:
        ride_worthiness = math.exp(-(route_distance_km - min(10.0, preferred_distance)) / max(preferred_distance, 1.0))

    travel_time_fit = round(max(0.0, min(1.0, travel_time_fit)), 6)
    ride_worthiness = round(max(0.0, min(1.0, ride_worthiness)), 6)
    return round(0.60 * travel_time_fit + 0.40 * ride_worthiness, 6), {
        "travel_time_fit": travel_time_fit,
        "ride_worthiness": ride_worthiness,
    }


def poi_quality(*, rating: object, review_count: object, maximum_review_count: int) -> float | None:
    """Use only available public Place fields and reweight missing components."""
    values: list[tuple[float, float]] = []
    try:
        if rating is not None:
            values.append((0.70, max(0.0, min(1.0, float(rating) / 5.0))))
    except (TypeError, ValueError):
        pass
    try:
        if review_count is not None and maximum_review_count > 0:
            confidence = math.log1p(max(0, int(review_count))) / math.log1p(maximum_review_count)
            values.append((0.30, max(0.0, min(1.0, confidence))))
    except (TypeError, ValueError):
        pass
    if not values:
        return None
    total_weight = sum(weight for weight, _ in values)
    return round(sum(weight * value for weight, value in values) / total_weight, 6)


def restaurant_score(*, area_score: float, context_score: float | None, poi_score: float | None) -> float:
    """Final documented 0.60 area + 0.20 context + 0.20 POI formula.

    If a public provider omitted a component, the available weights are
    normalized instead of inventing a value.
    """
    components: list[tuple[float, float]] = [(0.60, area_score)]
    if context_score is not None:
        components.append((0.20, context_score))
    if poi_score is not None:
        components.append((0.20, poi_score))
    weight = sum(item[0] for item in components)
    return round(sum(item_weight * value for item_weight, value in components) / weight, 6)
