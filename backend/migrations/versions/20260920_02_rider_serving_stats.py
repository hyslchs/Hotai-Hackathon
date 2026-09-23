"""rider area and neighbor serving tables"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_02"
down_revision = "20260920_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rider_area_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rider_key", sa.String(80), nullable=False),
        sa.Column("area_id", sa.String(80), nullable=False),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("visit_count", sa.Integer(), nullable=False),
        sa.Column("visit_ratio", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(160), sa.ForeignKey("model_releases.model_version"), nullable=False),
        sa.UniqueConstraint("rider_key", "area_id", "period", "model_version", name="uq_rider_area_period"),
    )
    op.create_table(
        "rider_neighbors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rider_key", sa.String(80), nullable=False),
        sa.Column("neighbor_rider_key", sa.String(80), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(160), sa.ForeignKey("model_releases.model_version"), nullable=False),
        sa.UniqueConstraint("rider_key", "neighbor_rider_key", "model_version", name="uq_rider_neighbor"),
    )


def downgrade() -> None:
    op.drop_table("rider_neighbors")
    op.drop_table("rider_area_stats")
