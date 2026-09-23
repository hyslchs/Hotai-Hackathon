"""add fare estimate aggregates and idempotent feedback events"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_04"
down_revision = "20260920_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fare_estimate_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_version", sa.String(length=160), nullable=False),
        sa.Column("distance_bin", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=False),
        sa.Column("region_label", sa.String(length=64), nullable=False),
        sa.Column("fare_p25", sa.Float(), nullable=False),
        sa.Column("fare_p75", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["model_version"], ["model_releases.model_version"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_version", "distance_bin", "period", "region_label", name="uq_fare_estimate_context"),
    )
    op.create_index("ix_fare_estimate_lookup", "fare_estimate_stats", ["model_version", "distance_bin", "period", "region_label"])
    op.create_table(
        "feedback_events",
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("place_key", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["recommendation_requests.request_id"]),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("request_id", "place_key", "action", name="uq_feedback_idempotency"),
    )
    op.create_index("ix_feedback_request_action", "feedback_events", ["request_id", "action"])


def downgrade() -> None:
    op.drop_index("ix_feedback_request_action", table_name="feedback_events")
    op.drop_table("feedback_events")
    op.drop_index("ix_fare_estimate_lookup", table_name="fare_estimate_stats")
    op.drop_table("fare_estimate_stats")
