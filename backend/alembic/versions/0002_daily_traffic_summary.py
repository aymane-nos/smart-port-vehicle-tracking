"""add daily_traffic_summary (ETL fact table)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# create_type=False : ce type ENUM existe déjà en base (créé par la migration
# 0001 pour `vehicles`/`detections`) — on le RÉFÉRENCE ici pour la nouvelle
# colonne, sans demander à Postgres de le recréer (sinon DuplicateObjectError).
vehicle_type_enum = postgresql.ENUM(
    "CAR", "TRUCK", "CONTAINER_TRUCK", "BUS", "MOTORCYCLE", "OTHER",
    name="vehicletype",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "daily_traffic_summary",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("gate_id", sa.String(length=50), nullable=False),
        sa.Column("vehicle_type", vehicle_type_enum, nullable=False),
        sa.Column("entries_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exits_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_vehicles_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_plate_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "summary_date", "gate_id", "vehicle_type", name="uq_daily_summary_partition"
        ),
    )
    op.create_index("ix_daily_traffic_summary_summary_date", "daily_traffic_summary", ["summary_date"])
    op.create_index("ix_daily_traffic_summary_gate_id", "daily_traffic_summary", ["gate_id"])


def downgrade() -> None:
    op.drop_table("daily_traffic_summary")
