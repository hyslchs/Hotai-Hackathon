from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    Area,
    AreaPeriodStat,
    DemoAlias,
    FareEstimateStat,
    ModelRelease,
    RiderAreaStat,
    RiderNeighbor,
    RiderProfile,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _version(report_hash: str) -> str:
    return f"taipei-serving-v1-{report_hash[:16]}"


def artifact_paths(root: Path) -> dict[str, Path]:
    return {
        "area": root / "area" / "area_artifact.json",
        "features": root / "features" / "feature_artifact.json",
        "profiles": root / "personalization" / "rider_profiles.parquet",
        "area_stats": root / "personalization" / "rider_area_stats.parquet",
        "neighbors": root / "personalization" / "rider_neighbors.parquet",
        "evaluation": root / "evaluation" / "personalized_evaluation_v2.json",
        "fare_estimates": root / "ride" / "fare_estimates.json",
    }


def load_serving_artifacts(session: Session, root: Path) -> dict[str, Any]:
    """Load only aggregate/salted fields; repeat loading of a release is a no-op."""
    paths = artifact_paths(root)
    if not all(path.is_file() for path in paths.values()):
        missing = [str(path) for path in paths.values() if not path.is_file()]
        raise FileNotFoundError(", ".join(missing))

    area_artifact = _read_json(paths["area"])
    feature_artifact = _read_json(paths["features"])
    evaluation = _read_json(paths["evaluation"])
    if evaluation["scope"] != "Taipei Demo only":
        raise ValueError("serving loader accepts Taipei Demo artifacts only")
    if evaluation["locked_config"]["selected_model"] != "area_a_plus_c":
        raise ValueError("D-009 requires the area_a_plus_c serving model")
    report_hash = str(evaluation["report_hash"])
    report_for_hash = dict(evaluation)
    report_for_hash.pop("report_hash", None)
    if report_hash != hashlib.sha256(
        json.dumps(
            report_for_hash,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest():
        raise ValueError("evaluation report hash mismatch")
    fare_estimates = _read_json(paths["fare_estimates"])
    if fare_estimates.get("artifact_type") != "train_fare_estimates" or fare_estimates.get("split") != "train":
        raise ValueError("fare estimates must be aggregate-only Train data")
    model_version = _version(report_hash)
    personalization_artifact = _read_json(root / "personalization" / "personalization_artifact.json")
    serving_config_json = json.dumps(
        {
            "weights": evaluation["locked_config"]["weights"]["area_a_plus_c"],
            "cohort_distance_reference": personalization_artifact["cohort_distance_reference"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    release = session.get(ModelRelease, model_version)
    release_exists = release is not None
    if release is None:
        session.add(
            ModelRelease(
                model_version=model_version,
                artifact_hash=report_hash,
                scope="Taipei Demo only",
                selected_model="area_a_plus_c",
                serving_config_json=serving_config_json,
                loaded_at=datetime.now(UTC),
            )
        )
    elif release.serving_config_json is None:
        release.serving_config_json = serving_config_json
    # PostgreSQL enforces this FK immediately; SQLite's default test setting does
    # not, so flush explicitly before batching dependent rows.
    session.flush()
    profiles = pq.read_table(paths["profiles"]).to_pylist()
    allowed_profile_fields = {
        "rider_key", "trip_count", "personalization_level", "p25_distance_km", "median_distance_km",
        "p75_distance_km", "p90_distance_km", "median_duration_min", "lunch_ratio",
        "morning_ratio", "afternoon_ratio", "dinner_ratio", "night_ratio", "weekend_ratio", "cross_area_ratio",
        "fare_midpoint_mean",
    }
    if release_exists:
        profiles_backfilled = 0
        for row in profiles:
            existing_profile = session.get(
                RiderProfile,
                {"rider_key": row["rider_key"], "model_version": model_version},
            )
            if existing_profile is None:
                continue
            changed = False
            for field in allowed_profile_fields - {"rider_key"}:
                if getattr(existing_profile, field) is None and row.get(field) is not None:
                    setattr(existing_profile, field, row[field])
                    changed = True
            profiles_backfilled += int(changed)
        existing_fares = session.scalar(
            select(FareEstimateStat.id).where(FareEstimateStat.model_version == model_version).limit(1)
        )
        if existing_fares is None:
            for row in fare_estimates["estimates"]:
                session.add(FareEstimateStat(model_version=model_version, **row))
        return {
            "model_version": model_version,
            "status": "already_loaded",
            "fare_estimates": len(fare_estimates["estimates"]),
            "profiles_backfilled": profiles_backfilled,
        }

    for row in area_artifact["areas"]:
        centroid = row["centroid"]
        session.add(
            Area(
                area_id=row["area_id"],
                model_version=model_version,
                centroid_lat=float(centroid["latitude"]),
                centroid_lng=float(centroid["longitude"]),
                cluster_size=int(row["sample_point_count"]),
                region_label=str(row["dominant_region"]),
                radius_p90_km=float(row["equivalent_radius_km_p90"]),
            )
        )
    for row in feature_artifact["features"]:
        session.add(
            AreaPeriodStat(
                area_id=row["area_id"],
                model_version=model_version,
                period=row["period"],
                weekday_class=row["weekday_class"],
                attraction_score=float(row["area_score"]),
                components_json=json.dumps(row["components"], ensure_ascii=False, sort_keys=True),
                evidence_json=json.dumps(row["evidence"], ensure_ascii=False, sort_keys=True),
            )
        )

    for row in profiles:
        session.add(
            RiderProfile(
                model_version=model_version,
                **{key: row.get(key) for key in allowed_profile_fields},
            )
        )

    area_stats = pq.read_table(paths["area_stats"]).to_pylist()
    for row in area_stats:
        session.add(
            RiderAreaStat(
                rider_key=row["rider_key"],
                area_id=row["area_id"],
                period=row["period"],
                visit_count=int(row["visit_count"]),
                visit_ratio=float(row["visit_ratio"]),
                model_version=model_version,
            )
        )
    neighbors = pq.read_table(paths["neighbors"]).to_pylist()
    for row in neighbors:
        session.add(
            RiderNeighbor(
                rider_key=row["rider_key"],
                neighbor_rider_key=row["neighbor_rider_key"],
                similarity=float(row["similarity"]),
                rank=int(row["rank"]),
                model_version=model_version,
            )
        )

    by_level = {row["personalization_level"]: row for row in sorted(profiles, key=lambda item: item["rider_key"])}
    aliases = (
        ("demo_rider_full", "完整資料", "full"),
        ("demo_rider_light", "少量資料", "light"),
        ("demo_rider_cold", "初次使用", "cold"),
    )
    for alias, label, level in aliases:
        rider = by_level.get(level)
        session.add(
            DemoAlias(
                model_version=model_version,
                alias=alias,
                rider_key=None if level == "cold" else rider["rider_key"],
                persona_label=label,
                personalization_level=level,
                trip_count=int(rider["trip_count"]) if rider else 0,
            )
        )
    for row in fare_estimates["estimates"]:
        session.add(FareEstimateStat(model_version=model_version, **row))
    return {
        "model_version": model_version,
        "status": "loaded",
        "areas": len(area_artifact["areas"]),
        "area_period_stats": len(feature_artifact["features"]),
        "profiles": len(profiles),
        "rider_area_stats": len(area_stats),
        "rider_neighbors": len(neighbors),
        "fare_estimates": len(fare_estimates["estimates"]),
    }
