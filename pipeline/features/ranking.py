from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .areas import assign_points
from .aggregate import context_key


@dataclass(frozen=True)
class RankedArea:
    rank: int
    area_id: str
    score: float
    components: dict[str, float]
    evidence: dict[str, Any]


def _feature_index(
    feature_artifact: dict[str, Any],
    period: str,
    weekday_class: str,
) -> dict[str, dict[str, Any]]:
    return {
        row["area_id"]: row
        for row in feature_artifact["features"]
        if row["period"] == period and row["weekday_class"] == weekday_class
    }


def _stable_score_key(item: dict[str, Any]) -> tuple[Any, ...]:
    evidence = item.get("evidence", {})
    return (
        -float(item["score"]),
        -int(evidence.get("visit_count", 0)),
        item["area_id"],
    )


def _rank_from_rows(rows: Sequence[dict[str, Any]], top_k: int) -> list[RankedArea]:
    ordered = sorted(rows, key=_stable_score_key)[:top_k]
    return [
        RankedArea(
            rank=index,
            area_id=row["area_id"],
            score=round(float(row["score"]), 12),
            components={
                key: round(float(value), 12)
                for key, value in row.get("components", {}).items()
            },
            evidence=dict(row.get("evidence", {})),
        )
        for index, row in enumerate(ordered, start=1)
    ]


def rank_area_attraction(
    feature_artifact: dict[str, Any],
    period: str,
    weekday_class: str,
    *,
    top_k: int = 10,
) -> list[RankedArea]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    rows = []
    for row in _feature_index(feature_artifact, period, weekday_class).values():
        rows.append(
            {
                "area_id": row["area_id"],
                "score": row["area_score"],
                "components": row["components"],
                "evidence": row["evidence"],
            }
        )
    return _rank_from_rows(rows, top_k)


def rank_origin_period(
    feature_artifact: dict[str, Any],
    origin_area_id: str,
    period: str,
    weekday_class: str,
    *,
    top_k: int = 10,
) -> list[RankedArea]:
    context = context_key(period, weekday_class)
    feature_rows = _feature_index(feature_artifact, period, weekday_class)
    popularity = feature_artifact.get("origin_period_popularity", {}).get(
        origin_area_id,
        {},
    ).get(context, [])
    popularity_by_area = {
        item["area_id"]: int(item["count"]) for item in popularity
    }
    rows = [
        {
            "area_id": area_id,
            "score": popularity_by_area.get(area_id, 0),
            "components": {
                "origin_period_count": float(
                    popularity_by_area.get(area_id, 0)
                )
            },
            "evidence": {
                "origin_period_count": popularity_by_area.get(area_id, 0),
                "area_score": feature_rows[area_id]["area_score"],
                "visit_count": feature_rows[area_id]["evidence"]["visit_count"],
            },
        }
        for area_id in feature_rows
    ]
    return _rank_from_rows(rows, top_k)


def _item_dict(item: RankedArea) -> dict[str, Any]:
    return {
        "rank": item.rank,
        "area_id": item.area_id,
        "score": item.score,
        "score_breakdown": item.components,
        "evidence": item.evidence,
    }


def recommend_demo_areas(
    area_artifact: dict[str, Any],
    feature_artifact: dict[str, Any],
    latitude: float,
    longitude: float,
    period: str,
    weekday_class: str,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    assignments = assign_points(
        area_artifact["model"],
        [(float(latitude), float(longitude))],
        area_artifact["metadata"]["cluster_to_area"],
    )
    origin = assignments[0]
    if origin.source == "model":
        ranked = rank_origin_period(
            feature_artifact,
            origin.area_id,
            period,
            weekday_class,
            top_k=top_k,
        )
        model_name = "origin_period_popularity"
    else:
        ranked = rank_area_attraction(
            feature_artifact,
            period,
            weekday_class,
            top_k=top_k,
        )
        model_name = "area_attraction_fallback"

    return {
        "model": model_name,
        "scope": "Taipei Demo only",
        "origin_area_id": origin.area_id,
        "origin_assignment_source": origin.source,
        "origin_region": origin.region,
        "fallback_used": origin.source != "model",
        "items": [_item_dict(item) for item in ranked],
    }
