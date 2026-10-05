"""initial schema: vehicles + detections

Revision ID: 0001
Revises:
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

vehicle_type_enum = sa.Enum(
    "CAR", "TRUCK", "CONTAINER_TRUCK", "BUS", "MOTORCYCLE", "OTHER",
    name="vehicletype",
)
vehicle_status_enum = sa.Enum("IN_PORT", "OUT", "UNKNOWN", name="vehiclestatus")
direction_enum = sa.Enum("IN", "OUT", name="direction")


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plate_number", sa.String(length=20), nullable=False),
        sa.Column("vehicle_type", vehicle_type_enum, nullable=False, server_default="OTHER"),
        sa.Column("status", vehicle_status_enum, nullable=False, server_default="UNKNOWN"),
        sa.Column("is_authorized", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_vehicles_plate_number", "vehicles", ["plate_number"], unique=True)
    op.create_index("ix_vehicles_status", "vehicles", ["status"])
    op.create_index("ix_vehicles_last_seen_at", "vehicles", ["last_seen_at"])

    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plate_raw", sa.String(length=20), nullable=False),
        sa.Column("plate_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("detection_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gate_id", sa.String(length=50), nullable=False),
        sa.Column("direction", direction_enum, nullable=False, server_default="IN"),
        sa.Column("vehicle_type", vehicle_type_enum, nullable=False, server_default="OTHER"),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("image_path", sa.String(), nullable=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_detections_plate_raw", "detections", ["plate_raw"])
    op.create_index("ix_detections_gate_id", "detections", ["gate_id"])
    op.create_index("ix_detections_track_id", "detections", ["track_id"])
    op.create_index("ix_detections_vehicle_id", "detections", ["vehicle_id"])
    op.create_index("ix_detections_timestamp", "detections", ["timestamp"])


def downgrade() -> None:
    op.drop_table("detections")
    op.drop_table("vehicles")
    direction_enum.drop(op.get_bind(), checkfirst=True)
    vehicle_status_enum.drop(op.get_bind(), checkfirst=True)
    vehicle_type_enum.drop(op.get_bind(), checkfirst=True)
