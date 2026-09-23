"""initial versioned serving schema"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_releases",
        sa.Column("model_version", sa.String(160), primary_key=True),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("selected_model", sa.String(64), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "areas",
        sa.Column("area_id", sa.String(80), primary_key=True),
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("model_releases.model_version"),
            primary_key=True,
        ),
        sa.Column("centroid_lat", sa.Float(), nullable=False),
        sa.Column("centroid_lng", sa.Float(), nullable=False),
        sa.Column("cluster_size", sa.Integer(), nullable=False),
        sa.Column("region_label", sa.String(64), nullable=False),
        sa.Column("radius_p90_km", sa.Float(), nullable=False),
    )
    op.create_index("ix_areas_model_region", "areas", ["model_version", "region_label"])
    op.create_table(
        "area_period_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(80), nullable=False),
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("model_releases.model_version"),
            nullable=False,
        ),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("weekday_class", sa.String(16), nullable=False),
        sa.Column("attraction_score", sa.Float(), nullable=False),
        sa.Column("components_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "area_id",
            "model_version",
            "period",
            "weekday_class",
            name="uq_area_period_context",
        ),
    )
    op.create_table(
        "rider_profiles",
        sa.Column("rider_key", sa.String(80), primary_key=True),
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("model_releases.model_version"),
            primary_key=True,
        ),
        sa.Column("trip_count", sa.Integer(), nullable=False),
        sa.Column("personalization_level", sa.String(16), nullable=False),
        sa.Column("median_distance_km", sa.Float()),
        sa.Column("p75_distance_km", sa.Float()),
        sa.Column("p90_distance_km", sa.Float()),
        sa.Column("median_duration_min", sa.Float()),
        sa.Column("lunch_ratio", sa.Float()),
        sa.Column("dinner_ratio", sa.Float()),
        sa.Column("night_ratio", sa.Float()),
        sa.Column("weekend_ratio", sa.Float()),
        sa.Column("cross_area_ratio", sa.Float()),
        sa.Column("fare_midpoint_mean", sa.Float()),
    )
    op.create_table(
        "demo_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("model_releases.model_version"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(48), nullable=False),
        sa.Column("rider_key", sa.String(80)),
        sa.Column("persona_label", sa.String(64), nullable=False),
        sa.Column("personalization_level", sa.String(16), nullable=False),
        sa.Column("trip_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("model_version", "alias", name="uq_demo_alias_model"),
    )
    op.create_table(
        "recommendation_requests",
        sa.Column("request_id", sa.String(80), primary_key=True),
        sa.Column(
            "model_version",
            sa.String(160),
            sa.ForeignKey("model_releases.model_version"),
            nullable=False,
        ),
        sa.Column("rider_alias", sa.String(48), nullable=False),
        sa.Column("origin_area_id", sa.String(80)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("personalization_level", sa.String(16), nullable=False),
        sa.Column("restaurant_source", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
    )
    op.create_table(
        "recommendation_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "request_id",
            sa.String(80),
            sa.ForeignKey("recommendation_requests.request_id"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("place_key", sa.String(80), nullable=False),
        sa.Column("area_id", sa.String(80), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("score_breakdown_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("request_id", "rank", name="uq_recommendation_rank"),
    )


def downgrade() -> None:
    op.drop_table("recommendation_items")
    op.drop_table("recommendation_requests")
    op.drop_table("demo_aliases")
    op.drop_table("rider_profiles")
    op.drop_table("area_period_stats")
    op.drop_index("ix_areas_model_region", table_name="areas")
    op.drop_table("areas")
    op.drop_table("model_releases")
