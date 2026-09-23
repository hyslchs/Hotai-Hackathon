from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Iterable, Sequence

EARTH_RADIUS_KM = 6371.0088
CITY_REGIONS = ("Taipei", "Taichung", "Kaohsiung", "Other/Unknown")


def degrees_to_radians(latitude: float, longitude: float) -> tuple[float, float]:
    return math.radians(float(latitude)), math.radians(float(longitude))


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    lat_a, lng_a = degrees_to_radians(latitude_a, longitude_a)
    lat_b, lng_b = degrees_to_radians(latitude_b, longitude_b)
    delta_lat = lat_b - lat_a
    delta_lng = lng_b - lng_a
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lng / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, value)))


def region_for_point(latitude: float, longitude: float) -> str:
    if 24.7 <= latitude <= 25.4 and 121.2 <= longitude <= 122.0:
        return "Taipei"
    if 23.8 <= latitude < 24.7 and 120.2 <= longitude < 121.4:
        return "Taichung"
    if 22.4 <= latitude < 23.8 and 120.0 <= longitude < 121.2:
        return "Kaohsiung"
    return "Other/Unknown"


def _point_key(point: tuple[float, float, str], index: int) -> str:
    latitude, longitude, region = point
    payload = f"{index}|{latitude:.8f}|{longitude:.8f}|{region}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def deterministic_stratified_sample(
    points: Sequence[tuple[float, float, str]],
    size: int,
) -> list[tuple[float, float, str]]:
    if size < 0:
        raise ValueError("sample size must be non-negative")
    if size > len(points):
        raise ValueError("sample size cannot exceed the coordinate pool")
    if size == len(points):
        return list(points)
    if size == 0:
        return []

    grouped: dict[str, list[tuple[str, tuple[float, float, str]]]] = defaultdict(list)
    for index, point in enumerate(points):
        grouped[point[2]].append((_point_key(point, index), point))

    for values in grouped.values():
        values.sort(key=lambda item: item[0])

    ranked: list[tuple[float, str, tuple[float, float, str]]] = []
    for region, values in sorted(grouped.items()):
        denominator = max(len(values), 1)
        for rank, (key, point) in enumerate(values):
            ranked.append((rank / denominator, f"{region}|{key}", point))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:size]]


def points_digest(points: Iterable[tuple[float, float, str]]) -> str:
    digest = hashlib.sha256()
    for latitude, longitude, region in points:
        digest.update(f"{latitude:.8f},{longitude:.8f},{region}\n".encode("utf-8"))
    return digest.hexdigest()
