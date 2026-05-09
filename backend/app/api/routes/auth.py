"""Authentication routes — fastapi-users JWT Bearer auth.

Endpoints (mounted in main.py):
  POST /api/auth/login    — returns access_token (Bearer JWT)
  POST /api/auth/logout   — invalidates token
  GET  /api/auth/me       — current user profile
  PATCH /api/auth/me      — update current user

Local dev: seed the first admin user with:
    make seed-admin
which runs app.scripts.seed_admin.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.database import get_db_session
from app.core.security import JWT_ALGORITHM, JWT_LIFETIME_SECONDS, JWT_SECRET
from app.models.auth import User

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ── Pydantic schemas ──────────────────────────────────────────────────────────


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass


# ── Database adapter ──────────────────────────────────────────────────────────


async def get_user_db(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
    yield SQLAlchemyUserDatabase(session, User)


# ── User manager ──────────────────────────────────────────────────────────────


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = JWT_SECRET
    verification_token_secret = JWT_SECRET


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


# ── Auth backend: Bearer JWT ──────────────────────────────────────────────────

bearer_transport = BearerTransport(tokenUrl="/api/auth/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=JWT_SECRET,
        lifetime_seconds=JWT_LIFETIME_SECONDS,
        algorithm=JWT_ALGORITHM,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# ── FastAPIUsers instance ─────────────────────────────────────────────────────

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Reusable dependencies for protected routes
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)

# ── Routers ───────────────────────────────────────────────────────────────────

# POST /login, POST /logout
auth_router = fastapi_users.get_auth_router(auth_backend)

# GET /me, PATCH /me
users_router = fastapi_users.get_users_router(UserRead, UserUpdate)
