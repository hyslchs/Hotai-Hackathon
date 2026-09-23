from datetime import datetime

from backend.app.models import Area, AreaPeriodStat, RiderAreaStat, RiderProfile
from backend.app.ranking import (
    contextual_fit,
    poi_quality,
    rank_areas,
    restaurant_score,
    serving_distance_budget_km,
)


def _area(area_id: str, latitude: float, longitude: float) -> Area:
    return Area(area_id=area_id, model_version="test-v1", centroid_lat=latitude, centroid_lng=longitude, cluster_size=100, region_label="Taipei", radius_p90_km=1.0)


def _stat(area_id: str, score: float) -> AreaPeriodStat:
    return AreaPeriodStat(area_id=area_id, model_version="test-v1", period="dinner", weekday_class="weekday", attraction_score=score, components_json="{}", evidence_json="{}")


def test_rank_areas_uses_locked_ac_weights_and_is_stable():
    profile = RiderProfile(
        rider_key="rider-safe", model_version="test-v1", trip_count=12, personalization_level="full",
        p25_distance_km=2.0, median_distance_km=4.0, p75_distance_km=6.0, p90_distance_km=9.0,
        median_duration_min=15.0, morning_ratio=0.1, lunch_ratio=0.2, afternoon_ratio=0.1,
        dinner_ratio=0.4, night_ratio=0.2, weekend_ratio=0.3, cross_area_ratio=0.5, fare_midpoint_mean=200.0,
    )
    result = rank_areas(
        origin_latitude=25.0478, origin_longitude=121.5170,
        areas=[_area("area-a", 25.06, 121.53), _area("area-b", 25.18, 121.64)],
        stats=[_stat("area-a", 0.4), _stat("area-b", 0.9)], profile=profile,
        rider_area_stats=[RiderAreaStat(rider_key="rider-safe", area_id="area-a", period="dinner", visit_count=9, visit_ratio=0.7, model_version="test-v1")],
        period="dinner", weekday_class="weekday", cohort_reference={"light": {"p25": 2, "p75": 6, "p90": 9}}, weights={"a": 0.3, "c": 0.7},
    )

    assert [row.area_id for row in result] == ["area-a", "area-b"]
    assert result[0].personal_mobility is not None
    assert result[0].score > result[1].score
    assert result == rank_areas(
        origin_latitude=25.0478, origin_longitude=121.5170,
        areas=[_area("area-a", 25.06, 121.53), _area("area-b", 25.18, 121.64)],
        stats=[_stat("area-a", 0.4), _stat("area-b", 0.9)], profile=profile,
        rider_area_stats=[RiderAreaStat(rider_key="rider-safe", area_id="area-a", period="dinner", visit_count=9, visit_ratio=0.7, model_version="test-v1")],
        period="dinner", weekday_class="weekday", cohort_reference={"light": {"p25": 2, "p75": 6, "p90": 9}}, weights={"a": 0.3, "c": 0.7},
    )


def test_rank_areas_reweights_to_a_for_cold_profile():
    result = rank_areas(
        origin_latitude=25.0478, origin_longitude=121.5170,
        areas=[_area("area-a", 25.06, 121.53), _area("area-b", 25.07, 121.54)],
        stats=[_stat("area-a", 0.4), _stat("area-b", 0.9)], profile=None, rider_area_stats=[],
        period="dinner", weekday_class="weekday", cohort_reference={}, weights={"a": 0.3, "c": 0.7},
    )

    assert [row.area_id for row in result] == ["area-b", "area-a"]
    assert all(row.personal_mobility is None for row in result)


def test_serving_distance_budget_is_bounded_by_persona_evidence():
    full = RiderProfile(
        rider_key="full", model_version="test-v1", trip_count=12, personalization_level="full",
        median_distance_km=4.0,
    )
    light = RiderProfile(
        rider_key="light", model_version="test-v1", trip_count=4, personalization_level="light",
        median_distance_km=7.95,
    )

    assert serving_distance_budget_km(None) == 8.0
    assert serving_distance_budget_km(full) == 6.0
    assert serving_distance_budget_km(light) == 10.0


def test_serving_distance_guardrail_excludes_remote_area_before_ranking():
    result = rank_areas(
        origin_latitude=25.0478,
        origin_longitude=121.5170,
        areas=[
            _area("near", 25.0500, 121.5200),
            _area("far", 24.9863, 121.5619),
        ],
        stats=[_stat("near", 0.40), _stat("far", 0.95)],
        profile=None,
        rider_area_stats=[],
        period="dinner",
        weekday_class="weekday",
        cohort_reference={},
        weights={"a": 0.3, "c": 0.7},
        distance_budget_km=8.0,
        proximity_weight=0.20,
    )

    assert [row.area_id for row in result] == ["near"]
    assert result[0].proximity_fit == 1.0


def test_restaurant_components_are_bounded_and_missing_poi_reweights():
    context, parts = contextual_fit(route_minutes=20, route_distance_km=5, profile=None, cohort_reference={})

    assert context == 1.0
    assert parts == {"travel_time_fit": 1.0, "ride_worthiness": 1.0}
    assert poi_quality(rating=4.5, review_count=None, maximum_review_count=0) == 0.9
    assert poi_quality(rating=None, review_count=None, maximum_review_count=0) is None
    assert restaurant_score(area_score=0.8, context_score=1.0, poi_score=None) == 0.85
