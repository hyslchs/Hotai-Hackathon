"""add safe live-serving profile and model configuration fields"""

from alembic import op
import sqlalchemy as sa


revision = "20260921_05"
down_revision = "20260920_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_releases", sa.Column("serving_config_json", sa.Text(), nullable=True))
    op.add_column("rider_profiles", sa.Column("p25_distance_km", sa.Float(), nullable=True))
    op.add_column("rider_profiles", sa.Column("morning_ratio", sa.Float(), nullable=True))
    op.add_column("rider_profiles", sa.Column("afternoon_ratio", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("rider_profiles", "afternoon_ratio")
    op.drop_column("rider_profiles", "morning_ratio")
    op.drop_column("rider_profiles", "p25_distance_km")
    op.drop_column("model_releases", "serving_config_json")
