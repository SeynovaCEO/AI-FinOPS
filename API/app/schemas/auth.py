"""
Authentication schemas.
"""

from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from app.core.security import validate_password
from .base import BaseSchema
from .user import User


class Token(BaseModel):
    """Token response schema."""
    access_token: str
    refresh_token: str
    token_type: str
    user: User


class TokenPayload(BaseModel):
    """Token payload schema."""
    sub: Optional[str] = None
    exp: Optional[int] = None
    type: Optional[str] = None
    tenant_id: Optional[str] = None


class RefreshToken(BaseModel):
    """Refresh token request schema."""
    refresh_token: str


class UserRegister(BaseModel):
    """User registration schema (requires organization)."""
    email: str
    password: str
    org_slug: str
    org_admin_name: str
    role: str = "viewer"

    @field_validator("password")
    def validate_password(cls, value: str) -> str:
        return validate_password(value)


class ForgotPasswordRequest(BaseModel):
    """Forgot password request schema."""
    email: str


class ResetPasswordRequest(BaseModel):
    """Reset password request schema."""
    email: str
    verification_code: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    def validate_new_password(cls, value: str) -> str:
        return validate_password(value)

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class MessageResponse(BaseModel):
    """Generic message response schema."""
    message: str