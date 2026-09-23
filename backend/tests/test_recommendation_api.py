from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.db import Base
from backend.app.models import Area, AreaPeriodStat, FareEstimateStat, FeedbackEvent, DemoAlias, ModelRelease, RiderProfile


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(ModelRelease(model_version="test-v1", artifact_hash="a" * 64, scope="Taipei Demo only", selected_model="area_a_plus_c", loaded_at=datetime.now(UTC)))
        session.add(Area(area_id="area-1", model_version="test-v1", centroid_lat=25.05, centroid_lng=121.52, cluster_size=100, region_label="Taipei", radius_p90_km=3))
        session.add(AreaPeriodStat(area_id="area-1", model_version="test-v1", period="dinner", weekday_class="weekday", attraction_score=0.8, components_json="{}", evidence_json="{}"))
        session.add(FareEstimateStat(model_version="test-v1", distance_bin="under_2km", period="dinner", region_label="Taipei", fare_p25=120, fare_p75=180, sample_count=100))
        session.add(FareEstimateStat(model_version="test-v1", distance_bin="2_to_5km", period="dinner", region_label="Taipei", fare_p25=120, fare_p75=180, sample_count=100))
        session.add(FareEstimateStat(model_version="test-v1", distance_bin="5_to_10km", period="dinner", region_label="Taipei", fare_p25=120, fare_p75=180, sample_count=100))
        session.add(FareEstimateStat(model_version="test-v1", distance_bin="10km_plus", period="dinner", region_label="Taipei", fare_p25=120, fare_p75=180, sample_count=100))
        session.add(RiderProfile(rider_key="salted-full", model_version="test-v1", trip_count=12, personalization_level="full", median_distance_km=4, p75_distance_km=6, p90_distance_km=10, median_duration_min=20, lunch_ratio=0.2, dinner_ratio=0.4, night_ratio=0.1, weekend_ratio=0.3, cross_area_ratio=0.5, fare_midpoint_mean=200))
        session.add(DemoAlias(model_version="test-v1", alias="demo_rider_full", rider_key="salted-full", persona_label="完整資料", personalization_level="full", trip_count=12))
        session.add(DemoAlias(model_version="test-v1", alias="demo_rider_light", rider_key="salted-full", persona_label="少量資料", personalization_level="light", trip_count=5))
        session.add(DemoAlias(model_version="test-v1", alias="demo_rider_cold", rider_key=None, persona_label="初次使用", personalization_level="cold", trip_count=0))
    monkeypatch.setattr(main.app.state, "session_factory", factory)
    return TestClient(main.app)


def _request(alias: str = "demo_rider_full") -> dict[str, object]:
    return {
        "rider_alias": alias,
        "location": {"name": "台北車站", "latitude": 25.0478, "longitude": 121.5170},
        "datetime": "2026-09-17T18:30:00+08:00",
    }


def test_recommendation_returns_deterministic_top_five_and_no_raw_identifier(client):
    first = client.post("/api/v1/recommendations", json=_request())
    second = client.post("/api/v1/recommendations", json=_request())

    assert first.status_code == second.status_code == 200
    first_body, second_body = first.json(), second.json()
    assert len(first_body["restaurants"]) == 5
    assert [item["place_id"] for item in first_body["restaurants"]] == [item["place_id"] for item in second_body["restaurants"]]
    assert [item["score"] for item in first_body["restaurants"]] == [item["score"] for item in second_body["restaurants"]]
    assert first_body["restaurants"][0]["score_breakdown"]["similar_riders"] is None
    assert first_body["calculation"]["model"] == "area_a_plus_c"
    assert first_body["calculation"]["stages"][-1]["results_returned"] == 5
    assert first_body["calculation"]["top_areas"][0]["area_id"] == "area-1"
    assert "salted-full" not in first.text


def test_cold_rider_marks_personal_components_unavailable(client):
    response = client.post("/api/v1/recommendations", json=_request("demo_rider_cold"))

    assert response.status_code == 200
    assert response.json()["personalization_level"] == "cold"
    assert all(item["score_breakdown"]["personal_mobility"] is None for item in response.json()["restaurants"])


def test_api_validates_timezone_and_unknown_alias(client):
    invalid = _request()
    invalid["datetime"] = "2026-09-17T18:30:00"
    invalid_response = client.post("/api/v1/recommendations", json=invalid)
    assert invalid_response.status_code == 422
    assert invalid_response.json()["error"]["code"] == "INVALID_REQUEST"

    unknown = _request("demo_rider_other")
    response = client.post("/api/v1/recommendations", json=unknown)
    assert response.status_code == 422
    assert response.json()["error"]["retryable"] is False


def test_cors_allows_the_frontend_recommendation_post(client):
    response = client.options(
        "/api/v1/recommendations",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]


def test_recommendation_uses_short_template_and_records_impressions(client):
    response = client.post("/api/v1/recommendations", json=_request())

    assert response.status_code == 200
    body = response.json()
    assert all(len(item["explanation"]) <= 60 for item in body["restaurants"])
    assert all("口味" not in item["explanation"] for item in body["restaurants"])
    with main.app.state.session_factory() as session:
        events = session.scalars(
            select(FeedbackEvent).where(
                FeedbackEvent.request_id == body["request_id"],
                FeedbackEvent.action == "impression",
            )
        ).all()
    assert len(events) == 5


def test_ride_estimate_and_feedback_are_safe_and_idempotent(client):
    recommendation = client.post("/api/v1/recommendations", json=_request()).json()
    restaurant = recommendation["restaurants"][0]
    ride_payload = {
        "request_id": recommendation["request_id"],
        "place_key": restaurant["place_id"],
        "origin": _request()["location"],
        "destination": {"name": restaurant["name"], **restaurant["location"]},
        "datetime": _request()["datetime"],
    }

    ride = client.post("/api/v1/ride/estimate", json=ride_payload)
    assert ride.status_code == 200
    assert ride.json()["fare_estimate"]["lower"] == 120
    assert "官方報價" in ride.json()["fare_estimate"]["label"]
    assert ride.json()["encoded_polyline"] is None
    assert "歷史車輛軌跡" in ride.json()["route_notice"]
    first = client.post("/api/v1/feedback", json={
        "request_id": recommendation["request_id"],
        "place_key": restaurant["place_id"],
        "action": "ride_clicked",
    })
    second = client.post("/api/v1/feedback", json={
        "request_id": recommendation["request_id"],
        "place_key": restaurant["place_id"],
        "action": "ride_clicked",
    })

    assert first.status_code == second.status_code == 200
    assert first.json()["recorded"] is True
    assert second.json()["recorded"] is False
    assert "salted-full" not in ride.text + first.text
