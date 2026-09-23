from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx


PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
PLACES_FIELD_MASK = "places.id,places.displayName,places.location,places.rating,places.userRatingCount,places.priceLevel,places.currentOpeningHours.openNow,places.primaryType,places.formattedAddress"
ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters"
ROUTE_DETAILS_FIELD_MASK = "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"
ROUTE_MATRIX_FIELD_MASK = "originIndex,destinationIndex,status,condition,distanceMeters,duration"


@dataclass(frozen=True)
class ProviderResult:
    source: str
    restaurants: list[dict[str, Any]]
    warning: str | None = None


@dataclass(frozen=True)
class RouteEstimate:
    distance_km: float
    minutes: int
    source: str


@dataclass(frozen=True)
class RouteDetails(RouteEstimate):
    encoded_polyline: str | None = None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    a, b, c, d = map(math.radians, (lat1, lng1, lat2, lng2))
    value = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


class PlacesProvider:
    def __init__(self, api_key: str, timeout_seconds: float = 2.5, client: httpx.Client | None = None):
        self.api_key, self.timeout_seconds, self.client = api_key, timeout_seconds, client

    def search(self, latitude: float, longitude: float, radius_meters: int) -> ProviderResult:
        if not self.api_key:
            return ProviderResult("fallback_fixture", [], "未設定 Places key，已使用展示資料。")
        body = {"includedTypes": ["restaurant"], "maxResultCount": 15, "rankPreference": "DISTANCE", "locationRestriction": {"circle": {"center": {"latitude": latitude, "longitude": longitude}, "radius": min(max(radius_meters, 1), 50000)}}}
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": PLACES_FIELD_MASK}
        try:
            client = self.client or httpx.Client(timeout=self.timeout_seconds)
            response = None
            for attempt in range(2):
                try:
                    response = client.post(PLACES_URL, json=body, headers=headers)
                except httpx.TimeoutException:
                    if attempt == 0:
                        time.sleep(random.uniform(0.01, 0.03))
                        continue
                    raise
                if response.status_code not in {408, 429} and response.status_code < 500:
                    break
                if attempt == 0:
                    time.sleep(random.uniform(0.01, 0.03))
            if response is None or response.status_code in {408, 429} or response.status_code >= 500:
                return ProviderResult("fallback_fixture", [], "即時餐廳服務暫時不可用，已使用展示資料。")
            response.raise_for_status()
            places = response.json().get("places", [])
        except (httpx.HTTPError, ValueError, TypeError):
            return ProviderResult("fallback_fixture", [], "即時餐廳服務暫時不可用，已使用展示資料。")
        seen, rows = set(), []
        for place in places:
            place_id = place.get("id")
            location = place.get("location") or {}
            name = (place.get("displayName") or {}).get("text")
            if not place_id or place_id in seen or not name or "latitude" not in location or "longitude" not in location:
                continue
            seen.add(place_id)
            opening = (place.get("currentOpeningHours") or {}).get("openNow")
            rows.append({
                "place_id": place_id,
                "name": name,
                "location": {"latitude": location["latitude"], "longitude": location["longitude"]},
                "rating": place.get("rating"),
                "review_count": place.get("userRatingCount"),
                "price_level": place.get("priceLevel"),
                "primary_type": place.get("primaryType"),
                "formatted_address": place.get("formattedAddress"),
                "open_status": "open" if opening is True else "closed" if opening is False else "unknown",
            })
        return ProviderResult("google_places", rows)


class RoutesProvider:
    def __init__(self, api_key: str, timeout_seconds: float = 2.5, client: httpx.Client | None = None):
        self.api_key, self.timeout_seconds, self.client = api_key, timeout_seconds, client

    def _fallback(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate:
        fallback_distance = round(_haversine_km(*origin, *destination) * 1.30, 2)
        fallback_minutes = max(5, round(fallback_distance / 0.32))
        return RouteEstimate(fallback_distance, fallback_minutes, "haversine_fallback")

    def _post(self, url: str, body: dict[str, Any], field_mask: str) -> Any | None:
        if not self.api_key:
            return None
        try:
            client = self.client or httpx.Client(timeout=self.timeout_seconds)
            response = None
            for attempt in range(2):
                try:
                    response = client.post(url, json=body, headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": field_mask})
                except httpx.TimeoutException:
                    if attempt == 0:
                        time.sleep(random.uniform(0.01, 0.03))
                        continue
                    raise
                if response.status_code not in {408, 429} and response.status_code < 500:
                    break
                if attempt == 0:
                    time.sleep(random.uniform(0.01, 0.03))
            if response is None or response.status_code in {408, 429} or response.status_code >= 500:
                return None
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            return None

    @staticmethod
    def _seconds(duration: object) -> int:
        return int(round(float(str(duration).rstrip("s"))))

    def estimate(self, origin: tuple[float, float], destination: tuple[float, float]) -> tuple[float, int, str]:
        fallback = self._fallback(origin, destination)
        body = {
            "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
            "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
            "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE", "computeAlternativeRoutes": False, "units": "METRIC",
        }
        payload = self._post(ROUTES_URL, body, ROUTES_FIELD_MASK)
        try:
            route = payload["routes"][0]
            estimate = RouteEstimate(round(float(route["distanceMeters"]) / 1000, 2), max(1, round(self._seconds(route["duration"]) / 60)), "google_routes")
        except (KeyError, IndexError, TypeError, ValueError):
            estimate = fallback
        return estimate.distance_km, estimate.minutes, estimate.source

    def estimate_matrix(self, origin: tuple[float, float], destinations: list[tuple[float, float]]) -> list[RouteEstimate]:
        fallbacks = [self._fallback(origin, destination) for destination in destinations]
        if not destinations or not self.api_key:
            return fallbacks
        body = {
            "origins": [{"waypoint": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}}}],
            "destinations": [
                {"waypoint": {"location": {"latLng": {"latitude": latitude, "longitude": longitude}}}}
                for latitude, longitude in destinations
            ],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "units": "METRIC",
        }
        payload = self._post(ROUTE_MATRIX_URL, body, ROUTE_MATRIX_FIELD_MASK)
        if not isinstance(payload, list):
            return fallbacks
        results = list(fallbacks)
        for element in payload:
            try:
                index = int(element["destinationIndex"])
                if element.get("condition") != "ROUTE_EXISTS" or not isinstance(element.get("status"), dict):
                    continue
                results[index] = RouteEstimate(
                    round(float(element["distanceMeters"]) / 1000, 2),
                    max(1, round(self._seconds(element["duration"]) / 60)),
                    "google_routes_matrix",
                )
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return results

    def route_details(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteDetails:
        fallback = self._fallback(origin, destination)
        body = {
            "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
            "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
            "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE", "computeAlternativeRoutes": False, "units": "METRIC",
        }
        payload = self._post(ROUTES_URL, body, ROUTE_DETAILS_FIELD_MASK)
        try:
            route = payload["routes"][0]
            return RouteDetails(
                distance_km=round(float(route["distanceMeters"]) / 1000, 2),
                minutes=max(1, round(self._seconds(route["duration"]) / 60)),
                source="google_routes",
                encoded_polyline=str(route["polyline"]["encodedPolyline"]),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return RouteDetails(fallback.distance_km, fallback.minutes, fallback.source)
