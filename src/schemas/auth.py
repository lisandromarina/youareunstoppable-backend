from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.models.subscription import Plan
from src.models.user import Role


def normalize_email(value: str) -> str:
    return value.strip().lower()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return normalize_email(value)


class GoogleRequest(BaseModel):
    id_token: str = Field(min_length=1)


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class SubscriptionResponse(BaseModel):
    id: UUID
    plan: Plan
    subscription_status: str | None
    current_period_end: datetime | None
    deleted_at: datetime | None
    deleted_reason: str | None


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    role: Role
    last_connection: datetime | None
    subscription: SubscriptionResponse
