import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.core.security import utcnow


class Origin(str, enum.Enum):
    catalog = "catalog"
    adaptive = "adaptive"


class DayStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class CommitmentStatus(str, enum.Enum):
    open = "open"
    done = "done"
    skipped = "skipped"


class Transformation(Base):
    __tablename__ = "transformations"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('catalog', 'adaptive')",
            name="ck_transformations_origin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), unique=True)
    started_on: Mapped[date] = mapped_column(Date)
    origin: Mapped[Origin] = mapped_column(
        Enum(Origin, name="transformation_origin", native_enum=False, length=16),
        default=Origin.catalog,
    )
    rationale: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    paths: Mapped[list["TransformationPath"]] = relationship(
        back_populates="transformation",
        cascade="all, delete-orphan",
        order_by="TransformationPath.sort_order",
    )
    days: Mapped[list["Day"]] = relationship(
        back_populates="transformation",
        cascade="all, delete-orphan",
    )


class TransformationPath(Base):
    __tablename__ = "transformation_paths"
    __table_args__ = (
        UniqueConstraint("transformation_id", "identity_id", name="uq_paths_identity"),
        CheckConstraint("day_in_phase >= 1", name="ck_paths_day_in_phase"),
        CheckConstraint("commitment_streak >= 0", name="ck_paths_commitment_streak"),
        CheckConstraint("current_phase_position >= 0", name="ck_paths_phase_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transformation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transformations.id", ondelete="CASCADE")
    )
    identity_id: Mapped[str] = mapped_column(String(64))
    direction_id: Mapped[str] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer)
    current_phase_position: Mapped[int] = mapped_column(Integer, default=0)
    day_in_phase: Mapped[int] = mapped_column(Integer, default=1)
    commitment_streak: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    transformation: Mapped[Transformation] = relationship(back_populates="paths")
    phases: Mapped[list["PathPhase"]] = relationship(
        back_populates="path",
        cascade="all, delete-orphan",
        order_by="PathPhase.position",
    )


class PathPhase(Base):
    __tablename__ = "path_phases"
    __table_args__ = (
        UniqueConstraint("path_id", "position", name="uq_path_phases_position"),
        CheckConstraint("length_days >= 1", name="ck_path_phases_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    path_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transformation_paths.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(String(120))
    length_days: Mapped[int] = mapped_column(Integer)
    catalog_phase_id: Mapped[str | None] = mapped_column(String(160))

    path: Mapped[TransformationPath] = relationship(back_populates="phases")
    commitments: Mapped[list["PlannedCommitment"]] = relationship(
        back_populates="phase",
        cascade="all, delete-orphan",
        order_by="PlannedCommitment.position",
    )


class PlannedCommitment(Base):
    __tablename__ = "planned_commitments"
    __table_args__ = (
        UniqueConstraint("phase_id", "position", name="uq_planned_commitments_position"),
        CheckConstraint("unlock_streak >= 0", name="ck_planned_commitments_unlock"),
        CheckConstraint(
            "recurrence IN ('daily', 'times_per_week', 'weekly', 'monthly')",
            name="ck_planned_commitments_recurrence",
        ),
        CheckConstraint(
            "times_per_week IS NULL OR (times_per_week >= 1 AND times_per_week <= 7)",
            name="ck_planned_commitments_times",
        ),
        CheckConstraint(
            "month_day IS NULL OR (month_day >= 1 AND month_day <= 28)",
            name="ck_planned_commitments_month_day",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phase_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("path_phases.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    unlock_streak: Mapped[int] = mapped_column(Integer)
    objective: Mapped[str] = mapped_column(Text)
    catalog_commitment_id: Mapped[str | None] = mapped_column(String(200))
    recurrence: Mapped[str] = mapped_column(String(32))
    times_per_week: Mapped[int | None] = mapped_column(Integer)
    weekdays: Mapped[list] = mapped_column(JSON, default=list)
    month_day: Mapped[int | None] = mapped_column(Integer)

    phase: Mapped[PathPhase] = relationship(back_populates="commitments")
    implementations: Mapped[list["PlannedImplementation"]] = relationship(
        back_populates="commitment",
        cascade="all, delete-orphan",
        order_by="PlannedImplementation.position",
    )


class PlannedImplementation(Base):
    __tablename__ = "planned_implementations"
    __table_args__ = (
        UniqueConstraint(
            "commitment_id",
            "position",
            name="uq_planned_implementations_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    commitment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("planned_commitments.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    commitment: Mapped[PlannedCommitment] = relationship(back_populates="implementations")


class Day(Base):
    __tablename__ = "days"
    __table_args__ = (
        UniqueConstraint("transformation_id", "calendar_date", name="uq_days_date"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_days_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transformation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transformations.id", ondelete="CASCADE")
    )
    calendar_date: Mapped[date] = mapped_column(Date)
    status: Mapped[DayStatus] = mapped_column(
        Enum(DayStatus, name="day_status", native_enum=False, length=16),
        default=DayStatus.open,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transformation: Mapped[Transformation] = relationship(back_populates="days")
    commitments: Mapped[list["DayCommitment"]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
    )


class DayCommitment(Base):
    __tablename__ = "day_commitments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'done', 'skipped')",
            name="ck_day_commitments_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    day_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("days.id", ondelete="CASCADE"))
    path_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transformation_paths.id", ondelete="SET NULL")
    )
    planned_commitment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("planned_commitments.id", ondelete="SET NULL")
    )
    implementation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("planned_implementations.id", ondelete="SET NULL")
    )
    status: Mapped[CommitmentStatus] = mapped_column(
        Enum(CommitmentStatus, name="commitment_status", native_enum=False, length=16),
        default=CommitmentStatus.open,
    )
    objective_snapshot: Mapped[str] = mapped_column(Text)
    title_snapshot: Mapped[str] = mapped_column(Text)

    day: Mapped[Day] = relationship(back_populates="commitments")
    path: Mapped[TransformationPath | None] = relationship()
    planned: Mapped[PlannedCommitment | None] = relationship()
    implementation: Mapped[PlannedImplementation | None] = relationship()
