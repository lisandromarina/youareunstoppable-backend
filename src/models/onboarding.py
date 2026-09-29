import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.security import utcnow


class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"
    __table_args__ = (
        UniqueConstraint("user_id", "step", name="uq_onboarding_steps_user_step"),
        CheckConstraint(
            "step IN ('begin', 'identity', 'direction')",
            name="ck_onboarding_steps_step",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    step: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
