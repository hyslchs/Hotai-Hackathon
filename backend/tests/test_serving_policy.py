from types import SimpleNamespace

from backend.app.recommendation import _diversified_shortlist


def _place(place_id: str, area_id: str, latitude: float, longitude: float) -> dict[str, object]:
    return {
        "place_id": place_id,
        "name": place_id,
        "location": {"latitude": latitude, "longitude": longitude},
        "source_area_id": area_id,
        "source_area_score": 0.8,
    }


def test_shortlist_round_robins_areas_before_filling_route_budget():
    rows = {
        f"place-{index}": _place(
            f"place-{index}",
            "area-a" if index < 4 else "area-b" if index < 8 else "area-c",
            25.05 + index * 0.001,
            121.52 + index * 0.001,
        )
        for index in range(10)
    }
    ranked_areas = [SimpleNamespace(area_id="area-a"), SimpleNamespace(area_id="area-b"), SimpleNamespace(area_id="area-c")]

    result = _diversified_shortlist(rows, ranked_areas, 25.0478, 121.5170, max_candidates=6)

    assert [row["source_area_id"] for row in result] == [
        "area-a", "area-b", "area-c", "area-a", "area-b", "area-c",
    ]


def test_shortlist_still_returns_five_when_only_one_area_has_candidates():
    rows = {
        f"place-{index}": _place(f"place-{index}", "area-a", 25.05 + index * 0.001, 121.52)
        for index in range(6)
    }
    ranked_areas = [SimpleNamespace(area_id="area-a")]

    result = _diversified_shortlist(rows, ranked_areas, 25.0478, 121.5170)

    assert len(result) == 6
