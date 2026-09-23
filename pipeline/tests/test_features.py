from __future__ import annotations

from collections import Counter

import numpy as np

from pipeline.features.aggregate import normalized_entropy, robust_minmax, robust_scale_params
from pipeline.features.areas import fallback_area_id
from pipeline.features.ranking import rank_area_attraction, rank_origin_period
from pipeline.features.personalization import (
    distance_fit,
    hash_rider_key,
    personalization_level,
)
from pipeline.evaluation.personalized import (
    ComponentWeights,
    MetricAccumulator,
    _combine_scores,
    _rank,
    compute_b_scores,
    compute_c_scores,
)


def _feature_artifact():
    rows = []
    for area_id, score, count in (
        ("taipei_area_0001", 0.8, 10),
        ("taipei_area_0002", 0.8, 10),
        ("taipei_area_0003", 0.2, 2),
    ):
        for period in ("dinner",):
            for weekday in ("weekday",):
                rows.append(
                    {
                        "area_id": area_id,
                        "period": period,
                        "weekday_class": weekday,
                        "context_key": f"{period}|{weekday}",
                        "area_score": score,
                        "components": {"visit_heat": score},
                        "evidence": {"visit_count": count},
                    }
                )
    return {
        "features": rows,
        "origin_period_popularity": {
            "taipei_area_0001": {
                "dinner|weekday": [
                    {"area_id": "taipei_area_0003", "count": 4},
                    {"area_id": "taipei_area_0002", "count": 1},
                ]
            }
        },
    }


def test_robust_minmax_clips_and_constant_is_zero_signal():
    params = robust_scale_params([1.0, 2.0, 3.0, 4.0, 5.0])
    assert robust_minmax(0.0, params) == 0.0
    assert robust_minmax(10.0, params) == 1.0
    constant = robust_scale_params([4.0, 4.0])
    assert robust_minmax(4.0, constant) == 0.0


def test_entropy_is_zero_for_one_source_and_one_for_uniform_two_sources():
    assert normalized_entropy({"one": 10}) == 0.0
    assert normalized_entropy({"one": 10, "two": 10}) == 1.0


def test_fallback_area_ids_are_explicit_and_stable():
    assert fallback_area_id("Taipei") == "fallback_taipei"
    assert fallback_area_id("not-a-region") == "fallback_other_unknown"


def test_area_ranking_uses_stable_area_id_tie_break():
    ranked = rank_area_attraction(_feature_artifact(), "dinner", "weekday")
    assert [item.area_id for item in ranked] == [
        "taipei_area_0001",
        "taipei_area_0002",
        "taipei_area_0003",
    ]


def test_origin_period_ranking_is_deterministic():
    ranked = rank_origin_period(
        _feature_artifact(),
        "taipei_area_0001",
        "dinner",
        "weekday",
        top_k=3,
    )
    assert [item.area_id for item in ranked] == [
        "taipei_area_0003",
        "taipei_area_0002",
        "taipei_area_0001",
    ]


def test_rider_key_is_salted_stable_and_never_contains_source_id():
    first = hash_rider_key(123456, "local-secret-one")
    repeated = hash_rider_key(123456, "local-secret-one")
    other_salt = hash_rider_key(123456, "local-secret-two")

    assert first == repeated
    assert first != other_salt
    assert "123456" not in first
    assert first.startswith("rider_")


def test_personalization_levels_match_trip_thresholds():
    assert personalization_level(2) == "cold"
    assert personalization_level(3) == "light"
    assert personalization_level(9) == "light"
    assert personalization_level(10) == "full"


def test_distance_fit_prefers_learned_range_and_declines_after_p90():
    at_p75 = distance_fit(7.0, 3.0, 7.0, 9.0)
    between_p75_p90 = distance_fit(8.0, 3.0, 7.0, 9.0)
    too_close = distance_fit(0.5, 3.0, 7.0, 9.0)
    too_far = distance_fit(20.0, 3.0, 7.0, 9.0)

    assert at_p75 == 1.0
    assert 0.65 < between_p75_p90 < at_p75
    assert 0.0 <= too_close < at_p75
    assert 0.0 <= too_far < at_p75


def test_c_scores_are_bounded_and_missing_profile_is_unavailable():
    profile = {
        "personalization_level": "light",
        "trip_count": 5,
        "median_distance_km": 5.0,
        "p25_distance_km": 3.0,
        "p90_distance_km": 9.0,
        "dinner_ratio": 0.6,
        "weekend_ratio": 0.2,
    }
    scores = compute_c_scores(
        profile,
        ["a", "b"],
        np.asarray([5.0, 20.0]),
        Counter({"a": 3}),
        "dinner",
        "weekday",
        {"light": {"p25": 2.0, "p75": 7.0, "p90": 10.0}},
    )

    assert scores is not None
    assert np.all((scores >= 0.0) & (scores <= 1.0))
    assert scores[0] > scores[1]
    assert compute_c_scores(None, ["a"], np.asarray([1.0]), Counter(), "dinner", "weekday", {}) is None


def test_b_requires_five_neighbors_and_returns_train_scaled_scores():
    neighbors = [(f"rider_{index}", 0.8) for index in range(5)]
    counts = {
        key: {"dinner": Counter({"a": 3, "b": 1})}
        for key, _similarity in neighbors
    }
    scores = compute_b_scores(
        "target",
        ["a", "b"],
        "dinner",
        neighbors,
        counts,
        {"p5": 0.0, "p95": 2.0},
        5,
    )

    assert scores is not None
    assert np.all((scores >= 0.0) & (scores <= 1.0))
    assert scores[0] > scores[1]
    assert compute_b_scores("target", ["a"], "dinner", neighbors[:4], counts, {"p5": 0.0, "p95": 2.0}, 5) is None


def test_missing_components_reweight_and_candidate_mask_excludes_areas():
    a = np.asarray([0.2, 0.8, 0.4])
    b = np.asarray([0.9, 0.1, 0.2])
    c = np.asarray([0.3, 0.6, 0.7])
    weights = ComponentWeights(0.4, 0.3, 0.3)

    assert np.allclose(_combine_scores(a, None, None, weights), a)
    assert np.allclose(_combine_scores(a, b, None, weights), (0.4 / 0.7) * a + (0.3 / 0.7) * b)
    assert np.allclose(_combine_scores(a, None, c, weights), (0.4 / 0.7) * a + (0.3 / 0.7) * c)
    assert np.allclose(_combine_scores(a, b, c, weights), 0.4 * a + 0.3 * b + 0.3 * c)
    assert _rank(a, np.asarray([True, False, True])).tolist() == [2, 0]


def test_metric_denominators_keep_unassigned_destinations_in_scope():
    metrics = MetricAccumulator()
    ranked = np.asarray([0, 1])
    mask = np.asarray([True, True])
    distances = np.asarray([2.0, 5.0])
    metrics.record(ranked, 0, mask, distances, ["a", "b"])
    metrics.record(ranked, None, mask, distances, ["a", "b"])
    result = metrics.finish(2)

    assert result["rows_in_scope"] == 2
    assert result["destination_coverage"] == 0.5
    assert result["candidate_coverage"] == 1.0
    assert result["hit_rate_at_5"] == 1.0
