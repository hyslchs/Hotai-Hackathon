from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pyarrow.parquet as pq

from pipeline.clustering.experiments import sha256_file
from pipeline.features.aggregate import context_key, load_feature_artifact
from pipeline.features.areas import assign_rows, load_area_artifact
from pipeline.features.personalization import (
    hash_rider_key,
    load_personalization_artifact,
)

PERSONALIZED_EVALUATION_VERSION = "phase3-taipei-personalized-evaluation-v2"
MODEL_NAMES = (
    "global_period_popularity",
    "origin_period_popularity",
    "area_attraction_a",
    "area_a_plus_c",
    "area_a_plus_b",
    "area_a_plus_b_plus_c",
)


@dataclass(frozen=True)
class ComponentWeights:
    a: float
    b: float
    c: float

    def as_dict(self) -> dict[str, float]:
        return {"a": self.a, "b": self.b, "c": self.c}


@dataclass
class MetricAccumulator:
    rows_in_scope: int = 0
    verified_destination_rows: int = 0
    candidate_covered_rows: int = 0
    hit5: int = 0
    hit10: int = 0
    mrr5_sum: float = 0.0
    ndcg5_sum: float = 0.0
    recommended_distance_sum: float = 0.0
    recommended_item_count: int = 0
    recommendation_counts: Counter[str] = field(default_factory=Counter)

    def record(
        self,
        ranked_indices: np.ndarray,
        actual_index: int | None,
        candidate_mask: np.ndarray,
        distances: np.ndarray,
        area_ids: list[str],
    ) -> None:
        self.rows_in_scope += 1
        top_items = ranked_indices[:5]
        for index in top_items:
            self.recommended_distance_sum += float(distances[int(index)])
            self.recommended_item_count += 1
            self.recommendation_counts[area_ids[int(index)]] += 1
        if actual_index is None:
            return
        self.verified_destination_rows += 1
        if bool(candidate_mask[actual_index]):
            self.candidate_covered_rows += 1
        positions = np.flatnonzero(ranked_indices == actual_index)
        if not len(positions):
            return
        position = int(positions[0])
        if position < 10:
            self.hit10 += 1
        if position < 5:
            self.hit5 += 1
            self.mrr5_sum += 1.0 / (position + 1)
            self.ndcg5_sum += 1.0 / math.log2(position + 2)

    def finish(self, total_area_count: int) -> dict[str, Any]:
        verified = self.verified_destination_rows
        recommended = self.recommended_item_count
        return {
            "rows_in_scope": self.rows_in_scope,
            "destination_coverage": (
                verified / self.rows_in_scope if self.rows_in_scope else 0.0
            ),
            "candidate_coverage": (
                self.candidate_covered_rows / verified if verified else 0.0
            ),
            "evaluated_verified_destinations": verified,
            "hit_rate_at_5": self.hit5 / verified if verified else 0.0,
            "hit_rate_at_10": self.hit10 / verified if verified else 0.0,
            "mrr_at_5": self.mrr5_sum / verified if verified else 0.0,
            "ndcg_at_5": self.ndcg5_sum / verified if verified else 0.0,
            "catalog_coverage": (
                len(self.recommendation_counts) / total_area_count
                if total_area_count
                else 0.0
            ),
            "average_recommended_distance_km": (
                self.recommended_distance_sum / recommended if recommended else 0.0
            ),
            "popularity_concentration": (
                max(self.recommendation_counts.values(), default=0) / recommended
                if recommended
                else 0.0
            ),
        }


@dataclass
class EvaluationQuestion:
    trip_id: int
    period: str
    weekday_class: str
    personalization_level: str
    actual_index: int | None
    candidate_mask: np.ndarray
    distances: np.ndarray
    global_scores: np.ndarray
    origin_scores: np.ndarray
    a_scores: np.ndarray
    b_scores: np.ndarray | None
    c_scores: np.ndarray | None


@dataclass
class EvaluationContext:
    input_path: Path
    area: dict[str, Any]
    features: dict[str, Any]
    personalization: dict[str, Any]
    rider_hash_salt: str
    area_ids: list[str]
    area_index: dict[str, int]
    centroid_latitudes: np.ndarray
    centroid_longitudes: np.ndarray
    profiles: dict[str, dict[str, Any]]
    rider_area_counts: dict[str, Counter[str]]
    rider_area_period_counts: dict[str, dict[str, Counter[str]]]
    neighbors: dict[str, list[tuple[str, float]]]
    a_by_context: dict[str, np.ndarray]
    global_by_context: dict[str, np.ndarray]
    origin_by_context: dict[tuple[str, str], np.ndarray]
    rider_key_cache: dict[int, str] = field(default_factory=dict)
    b_score_cache: dict[tuple[str, str], np.ndarray | None] = field(default_factory=dict)


def _score_vector(area_ids: list[str], values: dict[str, float | int]) -> np.ndarray:
    return np.asarray([float(values.get(area_id, 0.0)) for area_id in area_ids], dtype=np.float64)


def _build_context(
    input_path: Path,
    area_dir: Path,
    feature_path: Path,
    personalization_dir: Path,
    rider_hash_salt: str,
) -> EvaluationContext:
    if not rider_hash_salt:
        raise ValueError("RIDER_HASH_SALT must be configured")
    area = load_area_artifact(area_dir)
    features = load_feature_artifact(feature_path)
    personalization = load_personalization_artifact(personalization_dir)
    metadata = personalization["metadata"]
    input_sha256 = sha256_file(input_path)
    if area["metadata"]["input_sha256"] != input_sha256:
        raise ValueError("evaluation input does not match area artifact")
    if features["input_sha256"] != input_sha256 or features["fit_split"] != "train":
        raise ValueError("evaluation requires the matching Train feature artifact")
    if metadata["input_sha256"] != input_sha256 or metadata["fit_split"] != "train":
        raise ValueError("evaluation requires the matching Train personalization artifact")
    salt_fingerprint = hashlib.sha256(rider_hash_salt.encode("utf-8")).hexdigest()[:16]
    if metadata["salt_fingerprint"] != salt_fingerprint:
        raise ValueError("RIDER_HASH_SALT does not match personalization artifact")

    area_rows = sorted(area["metadata"]["areas"], key=lambda item: item["area_id"])
    area_ids = [row["area_id"] for row in area_rows]
    area_index = {area_id: index for index, area_id in enumerate(area_ids)}
    profiles = {row["rider_key"]: row for row in personalization["profiles"]}
    rider_area_counts: dict[str, Counter[str]] = defaultdict(Counter)
    rider_area_period_counts: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for row in personalization["area_stats"]:
        key = str(row["rider_key"])
        area_id = str(row["area_id"])
        period = str(row["period"])
        count = int(row["visit_count"])
        rider_area_counts[key][area_id] += count
        rider_area_period_counts[key][period][area_id] += count
    neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in personalization["neighbors"]:
        neighbors[str(row["rider_key"])].append(
            (str(row["neighbor_rider_key"]), float(row["similarity"]))
        )
    for values in neighbors.values():
        values.sort(key=lambda item: (-item[1], item[0]))

    a_by_context: dict[str, np.ndarray] = {}
    feature_groups: dict[str, dict[str, float]] = defaultdict(dict)
    for row in features["features"]:
        feature_groups[str(row["context_key"])][str(row["area_id"])] = float(row["area_score"])
    for context, values in feature_groups.items():
        a_by_context[context] = _score_vector(area_ids, values)

    global_by_context: dict[str, np.ndarray] = {}
    for context, rows in features["global_period_popularity"].items():
        global_by_context[str(context)] = _score_vector(
            area_ids,
            {str(row["area_id"]): int(row["count"]) for row in rows},
        )
    origin_by_context: dict[tuple[str, str], np.ndarray] = {}
    for origin_area, contexts in features["origin_period_popularity"].items():
        for context, rows in contexts.items():
            origin_by_context[(str(origin_area), str(context))] = _score_vector(
                area_ids,
                {str(row["area_id"]): int(row["count"]) for row in rows},
            )

    return EvaluationContext(
        input_path=input_path,
        area=area,
        features=features,
        personalization=personalization,
        rider_hash_salt=rider_hash_salt,
        area_ids=area_ids,
        area_index=area_index,
        centroid_latitudes=np.asarray([row["centroid"]["latitude"] for row in area_rows], dtype=np.float64),
        centroid_longitudes=np.asarray([row["centroid"]["longitude"] for row in area_rows], dtype=np.float64),
        profiles=profiles,
        rider_area_counts=dict(rider_area_counts),
        rider_area_period_counts={key: dict(value) for key, value in rider_area_period_counts.items()},
        neighbors=dict(neighbors),
        a_by_context=a_by_context,
        global_by_context=global_by_context,
        origin_by_context=origin_by_context,
    )


def _rider_key(context: EvaluationContext, rider_id: int) -> str:
    if rider_id not in context.rider_key_cache:
        context.rider_key_cache[rider_id] = hash_rider_key(rider_id, context.rider_hash_salt)
    return context.rider_key_cache[rider_id]


def _distance_vector(context: EvaluationContext, latitude: float, longitude: float) -> np.ndarray:
    lat1 = math.radians(float(latitude))
    lng1 = math.radians(float(longitude))
    lat2 = np.radians(context.centroid_latitudes)
    lng2 = np.radians(context.centroid_longitudes)
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    haversine = np.sin(delta_lat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lng / 2.0) ** 2
    straight_line = 6371.0088 * 2.0 * np.arcsin(np.minimum(1.0, np.sqrt(haversine)))
    return straight_line * 1.30


def _candidate_mask(distances: np.ndarray) -> np.ndarray:
    mask = distances <= 20.0
    if int(np.count_nonzero(mask)) < 10:
        mask = distances <= 30.0
    return mask


def compute_c_scores(
    profile: dict[str, Any] | None,
    area_ids: list[str],
    distances: np.ndarray,
    area_counts: Counter[str],
    period: str,
    weekday_class: str,
    cohort_reference: dict[str, Any],
) -> np.ndarray | None:
    if profile is None or profile["personalization_level"] == "cold":
        return None
    level = str(profile["personalization_level"])
    median = float(profile["median_distance_km"])
    if level == "full":
        p25 = float(profile["p25_distance_km"])
        p75 = float(profile["p75_distance_km"])
        p90 = float(profile["p90_distance_km"])
    else:
        reference = cohort_reference.get("light", {})
        p25 = min(median, float(reference.get("p25", median)))
        p75 = max(median, float(reference.get("p75", median)))
        p90 = max(p75 + 0.1, float(reference.get("p90", p75 + 0.1)))
    distance_scores = np.empty_like(distances, dtype=np.float64)
    below = distances < p25
    plateau = (distances >= p25) & (distances <= p75)
    shoulder = (distances > p75) & (distances <= p90)
    beyond = distances > p90
    distance_scores[below] = np.clip(0.35 + 0.65 * (distances[below] / p25), 0.0, 1.0)
    distance_scores[plateau] = 1.0
    distance_scores[shoulder] = 1.0 - 0.35 * (
        (distances[shoulder] - p75) / (p90 - p75)
    )
    distance_scores[beyond] = np.clip(
        0.65 * np.exp(-(distances[beyond] - p90) / p90),
        0.0,
        1.0,
    )
    period_ratio = float(profile.get(f"{period}_ratio", 0.0))
    trip_count = int(profile["trip_count"])
    time_habit = (period_ratio * trip_count + 1.0) / (trip_count + 5.0)
    weekend_ratio = float(profile["weekend_ratio"])
    weekday_ratio = weekend_ratio if weekday_class == "weekend" else 1.0 - weekend_ratio
    weekday_fit = (weekday_ratio * trip_count + 1.0) / (trip_count + 2.0)
    max_area_count = max(area_counts.values(), default=0)
    affinity = np.asarray(
        [
            math.log1p(area_counts.get(area_id, 0)) / math.log1p(max_area_count)
            if max_area_count
            else 0.0
            for area_id in area_ids
        ],
        dtype=np.float64,
    )
    scores = 0.50 * distance_scores + 0.20 * time_habit + 0.15 * weekday_fit + 0.15 * affinity
    return np.clip(scores, 0.0, 1.0)


def compute_b_scores(
    rider_key: str,
    area_ids: list[str],
    period: str,
    neighbors: list[tuple[str, float]],
    area_period_counts: dict[str, dict[str, Counter[str]]],
    b_scale: dict[str, float],
    min_effective_neighbors: int,
) -> np.ndarray | None:
    effective = [(key, similarity) for key, similarity in neighbors if similarity > 0.0]
    if len(effective) < min_effective_neighbors:
        return None
    denominator = sum(similarity for _, similarity in effective)
    if denominator <= 0.0:
        return None
    raw = np.zeros(len(area_ids), dtype=np.float64)
    area_index = {area_id: index for index, area_id in enumerate(area_ids)}
    for neighbor_key, similarity in effective:
        counts = area_period_counts.get(neighbor_key, {}).get(period, Counter())
        for area_id, count in counts.items():
            index = area_index.get(area_id)
            if index is not None:
                raw[index] += similarity * math.log1p(count)
    raw /= denominator
    p5 = float(b_scale["p5"])
    p95 = float(b_scale["p95"])
    if math.isclose(p5, p95, rel_tol=0.0, abs_tol=1e-12):
        return None
    return np.clip((raw - p5) / (p95 - p5), 0.0, 1.0)


def _iter_questions(
    context: EvaluationContext,
    split: str,
    batch_size: int = 50_000,
) -> Iterator[EvaluationQuestion]:
    parquet = pq.ParquetFile(context.input_path)
    columns = [
        "trip_id",
        "rider_id",
        "period",
        "weekday_class",
        "pickup_lat",
        "pickup_lng",
        "dropoff_lat",
        "dropoff_lng",
        "split",
    ]
    cluster_to_area = context.area["metadata"]["cluster_to_area"]
    metadata = context.personalization["metadata"]
    for batch in parquet.iter_batches(columns=columns, batch_size=batch_size):
        rows = [row for row in batch.to_pylist() if row["split"] == split]
        if not rows:
            continue
        pickups, dropoffs = assign_rows(
            context.area["model"],
            [(float(row["pickup_lat"]), float(row["pickup_lng"])) for row in rows],
            [(float(row["dropoff_lat"]), float(row["dropoff_lng"])) for row in rows],
            cluster_to_area,
        )
        for row, pickup, dropoff in zip(rows, pickups, dropoffs):
            if dropoff.region != "Taipei":
                continue
            actual_index = (
                context.area_index.get(dropoff.area_id)
                if dropoff.source == "model"
                else None
            )
            rider_key = _rider_key(context, int(row["rider_id"]))
            profile = context.profiles.get(rider_key)
            level = str(profile["personalization_level"]) if profile else "cold"
            period = str(row["period"])
            weekday = str(row["weekday_class"])
            key = context_key(period, weekday)
            distances = _distance_vector(
                context,
                float(row["pickup_lat"]),
                float(row["pickup_lng"]),
            )
            global_scores = context.global_by_context.get(
                key,
                np.zeros(len(context.area_ids), dtype=np.float64),
            )
            origin_scores = (
                context.origin_by_context.get((pickup.area_id, key), global_scores)
                if pickup.source == "model"
                else global_scores
            )
            a_scores = context.a_by_context[key]
            c_scores = compute_c_scores(
                profile,
                context.area_ids,
                distances,
                context.rider_area_counts.get(rider_key, Counter()),
                period,
                weekday,
                metadata["cohort_distance_reference"],
            )
            b_cache_key = (rider_key, period)
            if level == "full" and b_cache_key not in context.b_score_cache:
                context.b_score_cache[b_cache_key] = compute_b_scores(
                    rider_key,
                    context.area_ids,
                    period,
                    context.neighbors.get(rider_key, []),
                    context.rider_area_period_counts,
                    metadata["b_scale"],
                    int(metadata["config"]["min_effective_neighbors"]),
                )
            b_scores = context.b_score_cache.get(b_cache_key) if level == "full" else None
            yield EvaluationQuestion(
                trip_id=int(row["trip_id"]),
                period=period,
                weekday_class=weekday,
                personalization_level=level,
                actual_index=actual_index,
                candidate_mask=_candidate_mask(distances),
                distances=distances,
                global_scores=global_scores,
                origin_scores=origin_scores,
                a_scores=a_scores,
                b_scores=b_scores,
                c_scores=c_scores,
            )


def _combine_scores(
    a_scores: np.ndarray,
    b_scores: np.ndarray | None,
    c_scores: np.ndarray | None,
    weights: ComponentWeights,
) -> np.ndarray:
    components: list[tuple[float, np.ndarray]] = [(weights.a, a_scores)]
    if b_scores is not None and weights.b > 0.0:
        components.append((weights.b, b_scores))
    if c_scores is not None and weights.c > 0.0:
        components.append((weights.c, c_scores))
    total_weight = sum(weight for weight, _ in components)
    if total_weight <= 0.0:
        return a_scores.copy()
    result = np.zeros_like(a_scores, dtype=np.float64)
    for weight, values in components:
        result += (weight / total_weight) * values
    return np.clip(result, 0.0, 1.0)


def _rank(scores: np.ndarray, candidate_mask: np.ndarray) -> np.ndarray:
    masked = np.where(candidate_mask, scores, -np.inf)
    ordered = np.argsort(-masked, kind="stable")
    return ordered[candidate_mask[ordered]]


def _is_tuning_sample(trip_id: int) -> bool:
    digest = hashlib.blake2b(str(int(trip_id)).encode("ascii"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % 8 == 0


def _weight_grids() -> dict[str, list[ComponentWeights]]:
    ac = [ComponentWeights(round(a, 1), 0.0, round(1.0 - a, 1)) for a in np.arange(0.3, 1.0, 0.1)]
    ab = [ComponentWeights(round(a, 1), round(1.0 - a, 1), 0.0) for a in np.arange(0.3, 1.0, 0.1)]
    abc: list[ComponentWeights] = []
    for a_int in range(3, 9):
        for b_int in range(1, 10 - a_int):
            c_int = 10 - a_int - b_int
            if c_int >= 1:
                abc.append(ComponentWeights(a_int / 10, b_int / 10, c_int / 10))
    return {"area_a_plus_c": ac, "area_a_plus_b": ab, "area_a_plus_b_plus_c": abc}


def _weight_key(weights: ComponentWeights) -> str:
    return f"{weights.a:.1f}/{weights.b:.1f}/{weights.c:.1f}"


def _tune_weights(context: EvaluationContext) -> tuple[dict[str, ComponentWeights], dict[str, Any]]:
    grids = _weight_grids()
    stats: dict[str, dict[str, dict[str, float]]] = {
        model: {
            _weight_key(weights): {"questions": 0.0, "hit5": 0.0, "mrr5": 0.0}
            for weights in weights_list
        }
        for model, weights_list in grids.items()
    }
    sample_rows = 0
    for question in _iter_questions(context, "validation"):
        if question.actual_index is None or not _is_tuning_sample(question.trip_id):
            continue
        sample_rows += 1
        component_sets = {
            "area_a_plus_c": question.c_scores is not None,
            "area_a_plus_b": question.b_scores is not None,
            "area_a_plus_b_plus_c": question.b_scores is not None and question.c_scores is not None,
        }
        for model, available in component_sets.items():
            if not available:
                continue
            for weights in grids[model]:
                scores = _combine_scores(question.a_scores, question.b_scores, question.c_scores, weights)
                ranked = _rank(scores, question.candidate_mask)
                positions = np.flatnonzero(ranked == question.actual_index)
                position = int(positions[0]) if len(positions) else len(ranked)
                values = stats[model][_weight_key(weights)]
                values["questions"] += 1.0
                if position < 5:
                    values["hit5"] += 1.0
                    values["mrr5"] += 1.0 / (position + 1)

    defaults = {
        "area_a_plus_c": ComponentWeights(0.55, 0.0, 0.45),
        "area_a_plus_b": ComponentWeights(0.55, 0.45, 0.0),
        "area_a_plus_b_plus_c": ComponentWeights(0.40, 0.30, 0.30),
    }
    selected: dict[str, ComponentWeights] = {}
    report: dict[str, Any] = {"deterministic_sample_rows": sample_rows, "models": {}}
    for model, weights_list in grids.items():
        candidates: list[tuple[float, float, float, ComponentWeights, dict[str, float]]] = []
        for weights in weights_list:
            values = stats[model][_weight_key(weights)]
            questions = values["questions"]
            if questions <= 0:
                continue
            hit_rate = values["hit5"] / questions
            mrr = values["mrr5"] / questions
            candidates.append((hit_rate, mrr, weights.a, weights, values))
        if not candidates:
            selected[model] = defaults[model]
            report["models"][model] = {
                "selected_weights": defaults[model].as_dict(),
                "questions": 0,
                "hit_rate_at_5": None,
                "mrr_at_5": None,
                "used_default": True,
            }
            continue
        candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], _weight_key(item[3])))
        hit_rate, mrr, _a_weight, weights, values = candidates[0]
        selected[model] = weights
        report["models"][model] = {
            "selected_weights": weights.as_dict(),
            "questions": int(values["questions"]),
            "hit_rate_at_5": hit_rate,
            "mrr_at_5": mrr,
            "used_default": False,
        }
    return selected, report


def _new_group() -> dict[str, MetricAccumulator]:
    return {name: MetricAccumulator() for name in MODEL_NAMES}


def _model_scores(
    question: EvaluationQuestion,
    weights: dict[str, ComponentWeights],
) -> dict[str, np.ndarray]:
    return {
        "global_period_popularity": question.global_scores,
        "origin_period_popularity": question.origin_scores,
        "area_attraction_a": question.a_scores,
        "area_a_plus_c": _combine_scores(
            question.a_scores,
            None,
            question.c_scores,
            weights["area_a_plus_c"],
        ),
        "area_a_plus_b": _combine_scores(
            question.a_scores,
            question.b_scores,
            None,
            weights["area_a_plus_b"],
        ),
        "area_a_plus_b_plus_c": _combine_scores(
            question.a_scores,
            question.b_scores,
            question.c_scores,
            weights["area_a_plus_b_plus_c"],
        ),
    }


def _finish_groups(
    groups: dict[str, dict[str, MetricAccumulator]],
    total_area_count: int,
) -> dict[str, Any]:
    return {
        group: {
            model: accumulator.finish(total_area_count)
            for model, accumulator in model_values.items()
        }
        for group, model_values in sorted(groups.items())
    }


def _evaluate_split(
    context: EvaluationContext,
    split: str,
    weights: dict[str, ComponentWeights],
) -> dict[str, Any]:
    overall = _new_group()
    by_personalization: dict[str, dict[str, MetricAccumulator]] = defaultdict(_new_group)
    by_period: dict[str, dict[str, MetricAccumulator]] = defaultdict(_new_group)
    by_weekday_class: dict[str, dict[str, MetricAccumulator]] = defaultdict(_new_group)
    unavailability = Counter()
    rows = 0
    for question in _iter_questions(context, split):
        rows += 1
        if question.b_scores is None:
            unavailability["b_unavailable_rows"] += 1
        if question.c_scores is None:
            unavailability["c_unavailable_rows"] += 1
        scores_by_model = _model_scores(question, weights)
        for model, scores in scores_by_model.items():
            ranked = _rank(scores, question.candidate_mask)
            for accumulator in (
                overall[model],
                by_personalization[question.personalization_level][model],
                by_period[question.period][model],
                by_weekday_class[question.weekday_class][model],
            ):
                accumulator.record(
                    ranked,
                    question.actual_index,
                    question.candidate_mask,
                    question.distances,
                    context.area_ids,
                )
    total_area_count = len(context.area_ids)
    return {
        "split": split,
        "scope": "Taipei Demo only",
        "rows_in_scope": rows,
        "models": {
            model: accumulator.finish(total_area_count)
            for model, accumulator in overall.items()
        },
        "by_personalization": _finish_groups(dict(by_personalization), total_area_count),
        "by_period": _finish_groups(dict(by_period), total_area_count),
        "by_weekday_class": _finish_groups(dict(by_weekday_class), total_area_count),
        "component_unavailability": dict(sorted(unavailability.items())),
    }


def _select_serving_model(validation: dict[str, Any]) -> dict[str, Any]:
    models = validation["models"]
    ac = models["area_a_plus_c"]
    abc = models["area_a_plus_b_plus_c"]
    b_enabled = (
        abc["hit_rate_at_5"] > ac["hit_rate_at_5"]
        or (
            math.isclose(abc["hit_rate_at_5"], ac["hit_rate_at_5"], abs_tol=1e-12)
            and abc["mrr_at_5"] > ac["mrr_at_5"]
        )
    )
    eligible_models = list(MODEL_NAMES) if b_enabled else [
        "global_period_popularity",
        "origin_period_popularity",
        "area_attraction_a",
        "area_a_plus_c",
    ]
    simplicity = {name: index for index, name in enumerate(MODEL_NAMES)}
    selected = sorted(
        eligible_models,
        key=lambda name: (
            -models[name]["hit_rate_at_5"],
            -models[name]["mrr_at_5"],
            simplicity[name],
        ),
    )[0]
    origin = models["origin_period_popularity"]
    selected_metrics = models[selected]
    personalization_beats_origin = (
        selected in {"area_a_plus_c", "area_a_plus_b", "area_a_plus_b_plus_c"}
        and selected_metrics["hit_rate_at_5"] > origin["hit_rate_at_5"]
        and selected_metrics["mrr_at_5"] >= origin["mrr_at_5"]
    )
    return {
        "selected_model": selected,
        "b_enabled": b_enabled,
        "personalization_beats_origin_period": personalization_beats_origin,
        "selection_rule": "highest Validation HitRate@5, then MRR@5, then simpler model",
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_personalized_evaluation(
    input_path: Path,
    area_dir: Path,
    feature_path: Path,
    personalization_dir: Path,
    output_dir: Path,
    rider_hash_salt: str,
) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "personalized_evaluation_v2.json"
    markdown_path = output_dir / "personalized_evaluation_v2.md"
    context = _build_context(
        input_path,
        area_dir,
        feature_path,
        personalization_dir,
        rider_hash_salt,
    )
    expected = {
        "artifact_version": PERSONALIZED_EVALUATION_VERSION,
        "input_sha256": sha256_file(input_path),
        "area_artifact_hash": context.area["metadata"]["artifact_hash"],
        "feature_hash": context.features["feature_hash"],
        "personalization_hash": context.personalization["metadata"]["artifact_hash"],
        "evaluation_source_sha256": sha256_file(Path(__file__)),
    }
    if report_path.exists():
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        if all(existing.get(key) == value for key, value in expected.items()):
            return {"report": existing, "paths": {"json": report_path, "markdown": markdown_path}}
        raise ValueError(
            "a locked Test evaluation already exists for different artifacts; "
            "use a new versioned output directory instead of overwriting it"
        )

    weights, tuning = _tune_weights(context)
    validation = _evaluate_split(context, "validation", weights)
    selection = _select_serving_model(validation)
    locked_config = {
        "weights": {model: value.as_dict() for model, value in weights.items()},
        **selection,
        "locked_after_split": "validation",
    }
    test = _evaluate_split(context, "test", weights)
    report = {
        **expected,
        "scope": "Taipei Demo only",
        "fit_split": "train",
        "tuning_split": "validation",
        "test_used": True,
        "test_ran_after_lock": True,
        "tuning": tuning,
        "locked_config": locked_config,
        "validation": validation,
        "test": test,
        "limitations": [
            "結果只支持 Taipei Demo，不宣稱台中、高雄或全台泛化。",
            "離線題目評估的是 destination area，不代表已驗證餐廳口味偏好。",
            "actual destination 為 noise/fallback 的題目保留在 coverage 分母。",
            "Test 只使用 Validation 鎖定的權重與 component enablement。",
        ],
    }
    report["report_hash"] = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _write_json(report_path, report)
    markdown_path.write_text(
        "\n".join(
            [
                "# Taipei personalized offline evaluation",
                "",
                "Train fit、Validation 選擇、Test 鎖定後單次評估；不含 RiderId、TripId 或 raw rows。",
                "",
                f"- selected model: {selection['selected_model']}",
                f"- B enabled: {selection['b_enabled']}",
                f"- personalization beats Origin-Period: {selection['personalization_beats_origin_period']}",
                f"- Validation rows: {validation['rows_in_scope']}",
                f"- Test rows: {test['rows_in_scope']}",
                "",
                "| model | Validation HitRate@5 | Validation MRR@5 | Test HitRate@5 | Test MRR@5 |",
                "| --- | ---: | ---: | ---: | ---: |",
                *[
                    "| {name} | {vhit:.6f} | {vmrr:.6f} | {thit:.6f} | {tmrr:.6f} |".format(
                        name=name,
                        vhit=validation["models"][name]["hit_rate_at_5"],
                        vmrr=validation["models"][name]["mrr_at_5"],
                        thit=test["models"][name]["hit_rate_at_5"],
                        tmrr=test["models"][name]["mrr_at_5"],
                    )
                    for name in MODEL_NAMES
                ],
                "",
                "## Limitations",
                "",
                *[f"- {item}" for item in report["limitations"]],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"report": report, "paths": {"json": report_path, "markdown": markdown_path}}
