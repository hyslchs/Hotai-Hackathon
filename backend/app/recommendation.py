from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .config import settings
from .models import Area, AreaPeriodStat, DemoAlias, FareEstimateStat, FeedbackEvent, ModelRelease, RecommendationItem, RecommendationRequest, RiderAreaStat, RiderProfile
from .providers import PlacesProvider, RoutesProvider
from .ranking import (
    SERVING_PROXIMITY_WEIGHT,
    contextual_fit,
    haversine_km,
    poi_quality,
    rank_areas,
    restaurant_score,
    road_distance_km,
    serving_distance_budget_km,
)


RESTAURANTS = (
    ("demo-place-01", "暮色小館", 4.6, 680, 25.0521, 121.5222),
    ("demo-place-02", "島嶼食堂", 4.5, 603, 25.0338, 121.5434),
    ("demo-place-03", "拾光麵屋", 4.4, 526, 25.0516, 121.5572),
    ("demo-place-04", "山海餐桌", 4.3, 449, 25.0368, 121.5029),
    ("demo-place-05", "日常咖哩所", 4.2, 372, 25.0332, 121.5651),
)

MAX_ROUTE_CANDIDATES = 20
MAX_RESTAURANTS_PER_AREA = 2


class ServiceError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, status_code: int = 404):
        self.code, self.message, self.retryable, self.status_code = code, message, retryable, status_code


def _explanation(period: str, personal_mobility: float | None) -> str:
    labels = {
        "morning": "早晨", "lunch": "午餐", "afternoon": "下午",
        "dinner": "晚餐", "night": "夜間",
    }
    sentence = f"這一帶是{labels.get(period, '這個')}時段可以考慮的去處"
    if personal_mobility is not None:
        sentence += "，車程也在你常見的出行範圍內"
    return (sentence + "。")[:60]


def _ride_distance_bin(distance_km: float) -> str:
    if distance_km < 2:
        return "under_2km"
    if distance_km < 5:
        return "2_to_5km"
    if distance_km < 10:
        return "5_to_10km"
    return "10km_plus"


def _feedback_event_id(request_id: str, place_key: str, action: str) -> str:
    digest = hashlib.sha256(f"{request_id}|{place_key}|{action}".encode()).hexdigest()[:32]
    return f"evt_{digest}"


def _period(at: datetime) -> str:
    hour = at.hour
    if hour < 11:
        return "morning"
    if hour < 14:
        return "lunch"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "dinner"
    return "night"


def _weekday_class(at: datetime) -> str:
    return "weekend" if at.weekday() >= 5 else "weekday"


def _serving_config(release: ModelRelease) -> tuple[dict[str, object], dict[str, object]]:
    """Read versioned, aggregate-only settings; keep old releases compatible."""
    try:
        value = json.loads(release.serving_config_json or "{}")
    except (TypeError, ValueError):
        value = {}
    weights = value.get("weights", {}) if isinstance(value, dict) else {}
    cohort = value.get("cohort_distance_reference", {}) if isinstance(value, dict) else {}
    return (
        weights if isinstance(weights, dict) else {"a": 0.30, "c": 0.70},
        cohort if isinstance(cohort, dict) else {},
    )


def _fallback_places() -> list[dict[str, object]]:
    return [
        {
            "place_id": key,
            "name": name,
            "rating": rating,
            "review_count": reviews,
            "location": {"latitude": lat, "longitude": lng},
            "price_level": "DEMO_ONLY",
            "primary_type": None,
            "formatted_address": None,
            "open_status": "unknown",
        }
        for key, name, rating, reviews, lat, lng in RESTAURANTS
    ]


def _diversified_shortlist(
    provider_rows: dict[str, dict[str, object]],
    ranked_areas: list[object],
    origin_latitude: float,
    origin_longitude: float,
    *,
    max_candidates: int = MAX_ROUTE_CANDIDATES,
    max_per_area: int = MAX_RESTAURANTS_PER_AREA,
    minimum_candidates: int = 5,
) -> list[dict[str, object]]:
    """Select route candidates round-robin across ranked areas.

    Places may return many restaurants for the first area.  A round-robin pass
    prevents that provider response from occupying the whole Top 5, while the
    final fill keeps the demo usable when only one area has enough candidates.
    """
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in provider_rows.values():
        grouped[str(row["source_area_id"])].append(row)

    def candidate_key(row: dict[str, object]) -> tuple[float, str]:
        location = row["location"]
        return (
            road_distance_km(
                origin_latitude,
                origin_longitude,
                float(location["latitude"]),
                float(location["longitude"]),
            ),
            str(row["place_id"]),
        )

    for rows in grouped.values():
        rows.sort(key=candidate_key)

    area_ids = [str(area.area_id) for area in ranked_areas if str(area.area_id) in grouped]
    shortlist: list[dict[str, object]] = []
    for quota in range(max_per_area):
        for area_id in area_ids:
            rows = grouped[area_id]
            if len(rows) > quota:
                shortlist.append(rows[quota])
                if len(shortlist) >= max_candidates:
                    return shortlist

    # If the provider only returned one usable area, fill the remainder rather
    # than returning fewer than five restaurants.
    if len(shortlist) < min(minimum_candidates, len(provider_rows)):
        selected_ids = {str(row["place_id"]) for row in shortlist}
        remainder = sorted(
            (row for row in provider_rows.values() if str(row["place_id"]) not in selected_ids),
            key=candidate_key,
        )
        shortlist.extend(remainder[: max_candidates - len(shortlist)])
    return shortlist[:max_candidates]


def _release(session: Session) -> ModelRelease:
    release = session.scalar(select(ModelRelease).order_by(ModelRelease.loaded_at.desc()))
    if release is None:
        raise ServiceError("MODEL_UNAVAILABLE", "展示模型尚未載入，請先執行資料載入。", True, 503)
    return release


def list_demo_riders(session: Session) -> list[dict[str, object]]:
    release = _release(session)
    rows = session.scalars(
        select(DemoAlias).where(DemoAlias.model_version == release.model_version).order_by(DemoAlias.alias)
    ).all()
    return [{"alias": row.alias, "persona": row.persona_label, "trip_count": row.trip_count, "personalization_level": row.personalization_level} for row in rows]


def profile_for_alias(session: Session, alias: str) -> dict[str, object]:
    release = _release(session)
    demo = session.scalar(select(DemoAlias).where(DemoAlias.model_version == release.model_version, DemoAlias.alias == alias))
    if demo is None:
        raise ServiceError("RIDER_NOT_FOUND", "找不到指定的展示乘客。")
    profile = None if demo.rider_key is None else session.get(RiderProfile, {"rider_key": demo.rider_key, "model_version": release.model_version})
    return {
        "alias": demo.alias, "persona": demo.persona_label, "trip_count": demo.trip_count,
        "personalization_level": demo.personalization_level,
        "personal_mobility_available": profile is not None and demo.personalization_level != "cold",
        "similar_riders_available": False,
    }


def recommend(session: Session, alias: str, latitude: float, longitude: float, at: datetime) -> dict[str, object]:
    started = perf_counter()
    release = _release(session)
    demo = session.scalar(select(DemoAlias).where(DemoAlias.model_version == release.model_version, DemoAlias.alias == alias))
    if demo is None:
        raise ServiceError("RIDER_NOT_FOUND", "找不到指定的展示乘客。")
    profile = None if demo.rider_key is None else session.get(RiderProfile, {"rider_key": demo.rider_key, "model_version": release.model_version})
    areas = session.scalars(select(Area).where(Area.model_version == release.model_version)).all()
    if not areas:
        raise ServiceError("MODEL_UNAVAILABLE", "展示模型缺少區域資料，請重新載入資料。", True, 503)
    nearest = min(areas, key=lambda row: haversine_km(latitude, longitude, row.centroid_lat, row.centroid_lng))
    fallback = haversine_km(latitude, longitude, nearest.centroid_lat, nearest.centroid_lng) > max(nearest.radius_p90_km * 2, 5)
    period, weekday_class = _period(at), _weekday_class(at)
    stats = session.scalars(select(AreaPeriodStat).where(
        AreaPeriodStat.model_version == release.model_version,
        AreaPeriodStat.period == period,
        AreaPeriodStat.weekday_class == weekday_class,
    )).all()
    if not stats:
        raise ServiceError("MODEL_UNAVAILABLE", "展示模型缺少此時段的區域資料，請重新載入資料。", True, 503)
    rider_area_stats = [] if demo.rider_key is None else session.scalars(select(RiderAreaStat).where(
        RiderAreaStat.model_version == release.model_version,
        RiderAreaStat.rider_key == demo.rider_key,
        RiderAreaStat.period == period,
    )).all()
    weights, cohort_reference = _serving_config(release)
    distance_budget_km = serving_distance_budget_km(profile)
    area_started = perf_counter()
    ranked_areas = rank_areas(
        origin_latitude=latitude,
        origin_longitude=longitude,
        areas=areas,
        stats=stats,
        profile=profile,
        rider_area_stats=rider_area_stats,
        period=period,
        weekday_class=weekday_class,
        cohort_reference=cohort_reference,
        weights=weights,
        distance_budget_km=distance_budget_km,
        proximity_weight=SERVING_PROXIMITY_WEIGHT,
    )
    if not ranked_areas:
        raise ServiceError("MODEL_UNAVAILABLE", "目前位置附近沒有可用展示區域。", True, 503)
    area_elapsed_ms = (perf_counter() - area_started) * 1000
    ranked_by_id = {row.area_id: row for row in ranked_areas}

    places_started = perf_counter()
    places_provider = PlacesProvider(
        settings.google_places_api_key,
        settings.provider_timeout_seconds,
    )
    provider_rows: dict[str, dict[str, object]] = {}
    provider_warnings: list[str] = []
    places_calls = 0
    if settings.google_places_api_key:
        for ranked_area in ranked_areas:
            if len(provider_rows) >= 150 or places_calls >= 10:
                break
            result = places_provider.search(ranked_area.latitude, ranked_area.longitude, 3000)
            places_calls += 1
            if result.warning:
                provider_warnings.append(result.warning)
            rows = result.restaurants
            if 0 < len(rows) < 10 and places_calls < 10:
                expanded = places_provider.search(ranked_area.latitude, ranked_area.longitude, 6000)
                places_calls += 1
                if expanded.warning:
                    provider_warnings.append(expanded.warning)
                rows = expanded.restaurants
            for row in rows:
                if row.get("open_status") == "closed" or len(provider_rows) >= 150:
                    continue
                place_id = str(row["place_id"])
                candidate = dict(row)
                candidate["source_area_id"] = ranked_area.area_id
                candidate["source_area_score"] = ranked_area.score
                previous = provider_rows.get(place_id)
                if previous is None or float(candidate["source_area_score"]) > float(previous["source_area_score"]):
                    provider_rows[place_id] = candidate

    restaurant_source = "google_places" if len(provider_rows) >= 5 else "fallback_fixture"
    if restaurant_source == "fallback_fixture":
        provider_rows = {}
        top_area = ranked_areas[0]
        for row in _fallback_places():
            row["source_area_id"] = top_area.area_id
            row["source_area_score"] = top_area.score
            provider_rows[str(row["place_id"])] = row
    places_elapsed_ms = (perf_counter() - places_started) * 1000

    # Only the most relevant 20 candidates receive route estimates. This keeps
    # Google Routes cost bounded and prevents one area's Places response from
    # filling the entire shortlist.
    shortlist = _diversified_shortlist(provider_rows, ranked_areas, latitude, longitude)
    routes_started = perf_counter()
    routes = RoutesProvider(settings.google_routes_api_key, settings.provider_timeout_seconds)
    estimates = routes.estimate_matrix(
        (latitude, longitude),
        [(float(row["location"]["latitude"]), float(row["location"]["longitude"])) for row in shortlist],
    )
    routes_elapsed_ms = (perf_counter() - routes_started) * 1000
    maximum_reviews = max((int(row["review_count"] or 0) for row in shortlist), default=0)
    result_items: list[dict[str, object]] = []
    for place, route in zip(shortlist, estimates):
        lat, lng = float(place["location"]["latitude"]), float(place["location"]["longitude"])
        area = ranked_by_id[str(place["source_area_id"])]
        context_score, context_components = contextual_fit(
            route_minutes=route.minutes,
            route_distance_km=route.distance_km,
            profile=profile,
            cohort_reference=cohort_reference,
        )
        quality = poi_quality(
            rating=place.get("rating"),
            review_count=place.get("review_count"),
            maximum_review_count=maximum_reviews,
        )
        score = restaurant_score(area_score=area.score, context_score=context_score, poi_score=quality)
        result_items.append({
            "place_id": place["place_id"], "name": place["name"], "location": {"latitude": lat, "longitude": lng},
            "rating": place.get("rating"), "review_count": place.get("review_count"), "price_level": place.get("price_level"), "open_status": place.get("open_status"),
            "source_area_id": area.area_id, "area_score": area.score,
            "distance_km": route.distance_km, "estimated_travel_time_min": route.minutes,
            "score": score,
            "score_breakdown": {
                "area_attraction": area.area_attraction,
                "similar_riders": None,
                "personal_mobility": area.personal_mobility,
                "context_fit": context_score,
                "poi_quality": quality,
                **context_components,
            },
            "evidence": [
                {"type": "area_score", "value": area.score},
                {"type": "travel_estimate_source", "value": route.source},
                {"type": "restaurant_source", "value": restaurant_source},
            ],
            "explanation": _explanation(period, area.personal_mobility),
        })
    result_items.sort(key=lambda row: (-float(row["score"]), -int(row["review_count"] or 0), float(row["distance_km"]), str(row["place_id"])))
    result_items = result_items[:5]
    for index, item in enumerate(result_items, start=1):
        item["rank"] = index
    request_id = f"rec_{uuid4().hex[:16]}"
    session.add(RecommendationRequest(request_id=request_id, model_version=release.model_version, rider_alias=alias, origin_area_id=None if fallback else nearest.area_id, requested_at=at, personalization_level=demo.personalization_level, restaurant_source=restaurant_source, latency_ms=(perf_counter() - started) * 1000))
    # PostgreSQL checks the request foreign key immediately. Flush its parent
    # before batching items; SQLite's default setup otherwise hides this order.
    session.flush()
    for item in result_items:
        session.add(RecommendationItem(request_id=request_id, rank=int(item["rank"]), place_key=str(item["place_id"]), area_id=str(item["source_area_id"]), final_score=float(item["score"]), score_breakdown_json=json.dumps(item["score_breakdown"], sort_keys=True)))
        session.add(
            FeedbackEvent(
                event_id=_feedback_event_id(request_id, str(item["place_id"]), "impression"),
                request_id=request_id,
                place_key=str(item["place_id"]),
                action="impression",
                occurred_at=datetime.now(UTC),
            )
        )
    # Sessions deliberately disable autoflush; flush items and impressions so
    # the same transaction can safely serve a follow-up estimate or event.
    session.flush()
    warnings = ([] if restaurant_source == "google_places" else ["餐廳、評分與車程為合成展示資料，不代表真實店家或官方資訊。"])
    warnings.extend(dict.fromkeys(provider_warnings))
    if fallback:
        warnings.append("目前位置使用 Taipei fallback。")
    return {
        "request_id": request_id,
        "model_version": release.model_version,
        "personalization_level": demo.personalization_level,
        "restaurant_source": restaurant_source,
        "restaurants": result_items,
        "warnings": warnings,
        "calculation": {
            "model": release.selected_model,
            "period": period,
            "weekday_class": weekday_class,
            "origin_assignment": {
                "nearest_area_id": nearest.area_id,
                "used_taipei_fallback": fallback,
                "distance_budget_km": distance_budget_km,
                "proximity_weight": SERVING_PROXIMITY_WEIGHT,
            },
            "top_areas": [area.as_dict(index) for index, area in enumerate(ranked_areas, start=1)],
            "stages": [
                {"name": "area_ranking", "areas_scored": len(stats), "areas_selected": len(ranked_areas), "duration_ms": round(area_elapsed_ms, 2)},
                {"name": "restaurant_search", "area_queries": places_calls, "candidates_after_filter": len(provider_rows), "source": restaurant_source, "duration_ms": round(places_elapsed_ms, 2)},
                {"name": "route_estimation", "candidates_routed": len(shortlist), "duration_ms": round(routes_elapsed_ms, 2)},
                {
                    "name": "restaurant_ranking",
                    "results_returned": len(result_items),
                    "source_areas_in_shortlist": len({str(row["source_area_id"]) for row in shortlist}),
                    "max_restaurants_per_area": MAX_RESTAURANTS_PER_AREA,
                },
            ],
        },
    }


def estimate_ride(
    session: Session,
    request_id: str,
    place_key: str,
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    at: datetime,
) -> dict[str, object]:
    request = session.get(RecommendationRequest, request_id)
    if request is None:
        raise ServiceError("REQUEST_NOT_FOUND", "找不到推薦請求，請重新產生推薦。")
    item = session.scalar(
        select(RecommendationItem).where(
            RecommendationItem.request_id == request_id,
            RecommendationItem.place_key == place_key,
        )
    )
    if item is None:
        raise ServiceError("PLACE_NOT_IN_REQUEST", "此餐廳不在該次推薦中。")
    release = _release(session)
    areas = session.scalars(select(Area).where(Area.model_version == release.model_version)).all()
    nearest = min(areas, key=lambda row: haversine_km(origin_latitude, origin_longitude, row.centroid_lat, row.centroid_lng))
    route = RoutesProvider(settings.google_routes_api_key, settings.provider_timeout_seconds).route_details(
        (origin_latitude, origin_longitude), (destination_latitude, destination_longitude)
    )
    bucket = _ride_distance_bin(route.distance_km)
    period = _period(at)
    choices = (
        (period, nearest.region_label, "distance_period_region"),
        (period, "all_regions", "distance_period_all_regions"),
        ("all_periods", nearest.region_label, "distance_all_periods_region"),
        ("all_periods", "all_regions", "distance_only"),
    )
    estimate = None
    estimate_source = None
    for estimate_period, region, source in choices:
        estimate = session.scalar(
            select(FareEstimateStat).where(
                FareEstimateStat.model_version == release.model_version,
                FareEstimateStat.distance_bin == bucket,
                FareEstimateStat.period == estimate_period,
                FareEstimateStat.region_label == region,
            )
        )
        if estimate is not None:
            estimate_source = source
            break
    fare = None if estimate is None else {
        "lower": estimate.fare_p25,
        "upper": estimate.fare_p75,
        "sample_count": estimate.sample_count,
        "source": estimate_source,
        "label": "依 Train 歷史行程估算，非 yoxi 官方報價。",
    }
    return {
        "request_id": request_id,
        "place_key": place_key,
        "distance_km": route.distance_km,
        "estimated_travel_time_min": route.minutes,
        "route_source": route.source,
        "encoded_polyline": route.encoded_polyline,
        "route_notice": "此為目前建議路線，不是歷史車輛軌跡。",
        "fare_estimate": fare,
    }


def record_feedback(session: Session, request_id: str, place_key: str, action: str) -> dict[str, object]:
    item = session.scalar(
        select(RecommendationItem).where(
            RecommendationItem.request_id == request_id,
            RecommendationItem.place_key == place_key,
        )
    )
    if item is None:
        raise ServiceError("PLACE_NOT_IN_REQUEST", "此餐廳不在該次推薦中。")
    event_id = _feedback_event_id(request_id, place_key, action)
    values = {
        "event_id": event_id,
        "request_id": request_id,
        "place_key": place_key,
        "action": action,
        "occurred_at": datetime.now(UTC),
    }
    insert = postgresql_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(FeedbackEvent).values(**values).on_conflict_do_nothing(
        index_elements=["request_id", "place_key", "action"]
    ).returning(FeedbackEvent.event_id)
    inserted = session.scalar(statement)
    return {"event_id": event_id, "recorded": inserted is not None}
