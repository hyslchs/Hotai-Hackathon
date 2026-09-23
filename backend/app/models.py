from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ModelRelease(Base):
    __tablename__ = "model_releases"

    model_version: Mapped[str] = mapped_column(String(160), primary_key=True)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_model: Mapped[str] = mapped_column(String(64), nullable=False)
    serving_config_json: Mapped[str | None] = mapped_column(Text)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Area(Base):
    __tablename__ = "areas"
    __table_args__ = (Index("ix_areas_model_region", "model_version", "region_label"),)

    area_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), primary_key=True
    )
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lng: Mapped[float] = mapped_column(Float, nullable=False)
    cluster_size: Mapped[int] = mapped_column(Integer, nullable=False)
    region_label: Mapped[str] = mapped_column(String(64), nullable=False)
    radius_p90_km: Mapped[float] = mapped_column(Float, nullable=False)


class AreaPeriodStat(Base):
    __tablename__ = "area_period_stats"
    __table_args__ = (
        UniqueConstraint(
            "area_id", "model_version", "period", "weekday_class",
            name="uq_area_period_context",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    weekday_class: Mapped[str] = mapped_column(String(16), nullable=False)
    attraction_score: Mapped[float] = mapped_column(Float, nullable=False)
    components_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)


class RiderProfile(Base):
    __tablename__ = "rider_profiles"

    rider_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), primary_key=True
    )
    trip_count: Mapped[int] = mapped_column(Integer, nullable=False)
    personalization_level: Mapped[str] = mapped_column(String(16), nullable=False)
    p25_distance_km: Mapped[float | None] = mapped_column(Float)
    median_distance_km: Mapped[float | None] = mapped_column(Float)
    p75_distance_km: Mapped[float | None] = mapped_column(Float)
    p90_distance_km: Mapped[float | None] = mapped_column(Float)
    median_duration_min: Mapped[float | None] = mapped_column(Float)
    morning_ratio: Mapped[float | None] = mapped_column(Float)
    lunch_ratio: Mapped[float | None] = mapped_column(Float)
    afternoon_ratio: Mapped[float | None] = mapped_column(Float)
    dinner_ratio: Mapped[float | None] = mapped_column(Float)
    night_ratio: Mapped[float | None] = mapped_column(Float)
    weekend_ratio: Mapped[float | None] = mapped_column(Float)
    cross_area_ratio: Mapped[float | None] = mapped_column(Float)
    fare_midpoint_mean: Mapped[float | None] = mapped_column(Float)


class RiderAreaStat(Base):
    __tablename__ = "rider_area_stats"
    __table_args__ = (
        UniqueConstraint(
            "rider_key", "area_id", "period", "model_version",
            name="uq_rider_area_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    area_id: Mapped[str] = mapped_column(String(80), nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    visit_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), nullable=False
    )


class RiderNeighbor(Base):
    __tablename__ = "rider_neighbors"
    __table_args__ = (
        UniqueConstraint(
            "rider_key", "neighbor_rider_key", "model_version",
            name="uq_rider_neighbor",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    neighbor_rider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), nullable=False
    )


class DemoAlias(Base):
    __tablename__ = "demo_aliases"
    __table_args__ = (
        UniqueConstraint("model_version", "alias", name="uq_demo_alias_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(48), nullable=False)
    rider_key: Mapped[str | None] = mapped_column(String(80))
    persona_label: Mapped[str] = mapped_column(String(64), nullable=False)
    personalization_level: Mapped[str] = mapped_column(String(16), nullable=False)
    trip_count: Mapped[int] = mapped_column(Integer, nullable=False)


class RecommendationRequest(Base):
    __tablename__ = "recommendation_requests"

    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), nullable=False
    )
    rider_alias: Mapped[str] = mapped_column(String(48), nullable=False)
    origin_area_id: Mapped[str | None] = mapped_column(String(80))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    personalization_level: Mapped[str] = mapped_column(String(16), nullable=False)
    restaurant_source: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)


class RecommendationItem(Base):
    __tablename__ = "recommendation_items"
    __table_args__ = (
        UniqueConstraint("request_id", "rank", name="uq_recommendation_rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_requests.request_id"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    place_key: Mapped[str] = mapped_column(String(80), nullable=False)
    area_id: Mapped[str] = mapped_column(String(80), nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_breakdown_json: Mapped[str] = mapped_column(Text, nullable=False)


class FareEstimateStat(Base):
    __tablename__ = "fare_estimate_stats"
    __table_args__ = (
        UniqueConstraint(
            "model_version", "distance_bin", "period", "region_label",
            name="uq_fare_estimate_context",
        ),
        Index("ix_fare_estimate_lookup", "model_version", "distance_bin", "period", "region_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version: Mapped[str] = mapped_column(
        ForeignKey("model_releases.model_version"), nullable=False
    )
    distance_bin: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    region_label: Mapped[str] = mapped_column(String(64), nullable=False)
    fare_p25: Mapped[float] = mapped_column(Float, nullable=False)
    fare_p75: Mapped[float] = mapped_column(Float, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    __table_args__ = (
        UniqueConstraint("request_id", "place_key", "action", name="uq_feedback_idempotency"),
        Index("ix_feedback_request_action", "request_id", "action"),
    )

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_requests.request_id"), nullable=False
    )
    place_key: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
