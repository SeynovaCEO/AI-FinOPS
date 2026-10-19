from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.core import security
from app.core.config import settings
from app.core.security import pwd_context
from app.repositories.tenant_repo import tenant_repo
from app.repositories.user_repo import user_repo
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

RESET_CODE_TTL_MINUTES = 10
RESET_CODE_MAX_ATTEMPTS = 5


def _hash_reset_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _unique_slug(db: Session, name: str) -> str:
    """Build a URL-safe tenant slug from a company name, e.g. 'Test Co' -> 'test-co'.

    Appends -2, -3, ... if the slug is already taken.
    """
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:90] or "org"
    slug, n = base, 2
    while tenant_repo.get_by_slug(db, slug):
        slug = f"{base}-{n}"
        n += 1
    return slug


class AuthService:
    """Authentication service."""

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
        """Authenticate user with email and password."""
        user = user_repo.get_by_email(db, email=email)
        if not user:
            return None
        if not pwd_context.verify(password, user.password_hash):
            return None
        return user

    @staticmethod
    def create_access_token(user: models.User) -> str:
        """Create access token for user."""
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return security.create_access_token(
            user.id,
            expires_delta=access_token_expires,
            extra_claims={"tenant_id": user.tenant_id}
        )

    @staticmethod
    def create_refresh_token(user: models.User) -> str:
        """Create refresh token for user."""
        refresh_token_expires = timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
        return security.create_refresh_token(
            user.id,
            expires_delta=refresh_token_expires,
            extra_claims={"tenant_id": user.tenant_id}
        )

    @staticmethod
    def login(db: Session, email: str, password: str) -> Optional[schemas.Token]:
        """Login user and return tokens."""
        user = AuthService.authenticate_user(db, email, password)
        if not user or not user.is_active:
            return None

        access_token = AuthService.create_access_token(user)
        refresh_token = AuthService.create_refresh_token(user)

        return schemas.Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user,
        )

    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Optional[schemas.Token]:
        """Refresh access token using refresh token."""
        try:
            payload = security.verify_token(refresh_token)
            if payload.get("type") != "refresh":
                return None
            user_id = payload.get("sub")
            tenant_id = payload.get("tenant_id")
        except Exception:
            return None

        user = user_repo.get(db, id=user_id)
        if not user or not user.is_active:
            return None

        access_token = AuthService.create_access_token(user)
        new_refresh_token = AuthService.create_refresh_token(user)

        return schemas.Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            user=user,
        )

    @staticmethod
    def create_user(db: Session, user_in: schemas.UserCreate) -> models.User:
        """Create a new user."""
        # Check if user already exists
        existing_user = user_repo.get_by_email(db, email=user_in.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Hash password
        hashed_password = security.get_password_hash(user_in.password)
        
        # Create user directly with model
        user = models.User(
            email=user_in.email,
            password_hash=hashed_password,
            role=user_in.role,
            tenant_id=user_in.tenant_id,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def register_user(db: Session, user_reg: schemas.UserRegister) -> models.User:
        """Self-service signup: create a new organization with the user as its owner."""
        org_in = schemas.OrgAdminCreate(
            org_name=user_reg.company_name,
            org_slug=_unique_slug(db, user_reg.company_name),
            admin_email=user_reg.email,
            admin_password=user_reg.password,
            admin_name=user_reg.username,
        )
        # Raises ValueError("Email already registered") for duplicates
        _, user = TenantService.create_tenant_with_admin(db, org_in)
        return user

    @staticmethod
    def request_password_reset(db: Session, email: str) -> None:
        """Generate a one-time reset code for the user, if the email exists.

        Silently does nothing for unknown emails so callers cannot probe
        which accounts exist.
        """
        user = user_repo.get_by_email(db, email=email)
        if not user or not user.is_active:
            return

        code = f"{secrets.randbelow(1_000_000):06d}"
        user.reset_code_hash = _hash_reset_code(code)
        user.reset_code_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=RESET_CODE_TTL_MINUTES
        )
        user.reset_code_attempts = 0
        db.add(user)
        db.commit()

        # TODO: send by email once an email provider is configured.
        if settings.ENVIRONMENT == "development":
            logger.warning("Password reset code for %s: %s", user.email, code)
        else:
            logger.warning(
                "Password reset requested for %s but email delivery is not configured",
                user.email,
            )

    @staticmethod
    def reset_password(db: Session, email: str, code: str, new_password: str) -> None:
        """Verify the reset code and set a new password."""
        invalid = ValueError("Invalid or expired verification code")

        user = user_repo.get_by_email(db, email=email)
        if not user or not user.reset_code_hash or not user.reset_code_expires_at:
            raise invalid

        if (
            datetime.now(timezone.utc) > user.reset_code_expires_at
            or user.reset_code_attempts >= RESET_CODE_MAX_ATTEMPTS
        ):
            AuthService._clear_reset_code(db, user)
            raise invalid

        if not hmac.compare_digest(user.reset_code_hash, _hash_reset_code(code.strip())):
            user.reset_code_attempts += 1
            db.add(user)
            db.commit()
            raise invalid

        user.password_hash = security.get_password_hash(new_password)
        AuthService._clear_reset_code(db, user)

    @staticmethod
    def _clear_reset_code(db: Session, user: models.User) -> None:
        user.reset_code_hash = None
        user.reset_code_expires_at = None
        user.reset_code_attempts = 0
        db.add(user)
        db.commit()