from __future__ import annotations

import json

import httpx
import pytest

from backend.app.providers import ROUTE_DETAILS_FIELD_MASK, ROUTE_MATRIX_FIELD_MASK, PLACES_FIELD_MASK, ROUTES_FIELD_MASK, PlacesProvider, RoutesProvider


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_places_requires_key_without_making_network_call():
    result = PlacesProvider("").search(25.05, 121.52, 3000)

    assert result.source == "fallback_fixture"
    assert result.restaurants == []


@pytest.mark.parametrize("status", [429, 500])
def test_places_provider_falls_back_for_retryable_statuses(status):
    provider = PlacesProvider("test-key", client=_client(lambda request: httpx.Response(status)))

    result = provider.search(25.05, 121.52, 3000)

    assert result.source == "fallback_fixture"
    assert result.warning


def test_places_provider_uses_required_mask_and_deduplicates():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"places": [
            {"id": "place-1", "displayName": {"text": "測試店"}, "location": {"latitude": 25.05, "longitude": 121.52}, "rating": 4.5, "userRatingCount": 10, "currentOpeningHours": {"openNow": True}},
            {"id": "place-1", "displayName": {"text": "重複店"}, "location": {"latitude": 25.06, "longitude": 121.53}},
            {"id": "incomplete"},
        ]})

    result = PlacesProvider("test-key", client=_client(handler)).search(25.05, 121.52, 99999)

    assert result.source == "google_places"
    assert [item["place_id"] for item in result.restaurants] == ["place-1"]
    assert seen["headers"]["x-goog-fieldmask"] == PLACES_FIELD_MASK
    assert seen["json"]["locationRestriction"]["circle"]["radius"] == 50000
    assert seen["json"]["maxResultCount"] == 15


def test_places_retries_once_then_uses_successful_response(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429 if len(calls) == 1 else 200, json={"places": [{"id": "place-1", "displayName": {"text": "測試店"}, "location": {"latitude": 25.05, "longitude": 121.52}}]})

    monkeypatch.setattr("backend.app.providers.time.sleep", lambda _value: None)
    result = PlacesProvider("test-key", client=_client(handler)).search(25.05, 121.52, 3000)

    assert result.source == "google_places"
    assert len(calls) == 2


@pytest.mark.parametrize("response", [
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request)),
    lambda request: httpx.Response(429),
    lambda request: httpx.Response(500),
    lambda request: httpx.Response(200, json={"routes": []}),
])
def test_routes_provider_falls_back_on_failure(response):
    distance, minutes, source = RoutesProvider("test-key", client=_client(response)).estimate((25.05, 121.52), (25.06, 121.53))

    assert source == "haversine_fallback"
    assert distance > 0
    assert minutes >= 5


def test_routes_provider_requests_minimal_mask_and_parses_response():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        return httpx.Response(200, json={"routes": [{"distanceMeters": 2500, "duration": "600s"}]})

    distance, minutes, source = RoutesProvider("test-key", client=_client(handler)).estimate((25.05, 121.52), (25.06, 121.53))

    assert (distance, minutes, source) == (2.5, 10, "google_routes")
    assert seen["headers"]["x-goog-fieldmask"] == ROUTES_FIELD_MASK


def test_routes_matrix_uses_one_origin_and_preserves_destination_order():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json=[
            {"originIndex": 0, "destinationIndex": 1, "status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 3000, "duration": "660s"},
            {"originIndex": 0, "destinationIndex": 0, "status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 1200, "duration": "300s"},
        ])

    result = RoutesProvider("test-key", client=_client(handler)).estimate_matrix(
        (25.05, 121.52), [(25.06, 121.53), (25.07, 121.54)]
    )

    assert [(item.distance_km, item.minutes, item.source) for item in result] == [
        (1.2, 5, "google_routes_matrix"), (3.0, 11, "google_routes_matrix")
    ]
    assert len(seen["json"]["origins"]) == 1
    assert len(seen["json"]["destinations"]) == 2
    assert seen["headers"]["x-goog-fieldmask"] == ROUTE_MATRIX_FIELD_MASK


def test_route_details_returns_encoded_polyline_only_when_available():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        return httpx.Response(200, json={"routes": [{
            "distanceMeters": 2500, "duration": "600s", "polyline": {"encodedPolyline": "abc123"}
        }]})

    result = RoutesProvider("test-key", client=_client(handler)).route_details((25.05, 121.52), (25.06, 121.53))

    assert result.encoded_polyline == "abc123"
    assert result.source == "google_routes"
    assert seen["headers"]["x-goog-fieldmask"] == ROUTE_DETAILS_FIELD_MASK
