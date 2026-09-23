"""allow prefixed salted rider keys"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_03"
down_revision = "20260920_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in (
        ("rider_profiles", "rider_key"),
        ("rider_area_stats", "rider_key"),
        ("rider_neighbors", "rider_key"),
        ("rider_neighbors", "neighbor_rider_key"),
        ("demo_aliases", "rider_key"),
    ):
        op.alter_column(table, column, existing_type=sa.String(64), type_=sa.String(80))


def downgrade() -> None:
    for table, column in (
        ("demo_aliases", "rider_key"),
        ("rider_neighbors", "neighbor_rider_key"),
        ("rider_neighbors", "rider_key"),
        ("rider_area_stats", "rider_key"),
        ("rider_profiles", "rider_key"),
    ):
        op.alter_column(table, column, existing_type=sa.String(80), type_=sa.String(64))
