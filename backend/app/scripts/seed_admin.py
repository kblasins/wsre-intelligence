"""One-time admin user seeder.

Usage:
    cd backend && python -m app.scripts.seed_admin

Creates the admin user from settings.admin_email / settings.admin_password if
it doesn't already exist. Safe to re-run — idempotent.
"""

from __future__ import annotations

import asyncio

import structlog

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging

log = structlog.get_logger(__name__)


async def seed_admin() -> None:
    from fastapi_users.exceptions import UserAlreadyExists
    from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

    from app.api.routes.auth import UserCreate, UserManager
    from app.models.auth import User

    configure_logging()

    async with AsyncSessionFactory() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        manager = UserManager(user_db)

        try:
            user = await manager.create(
                UserCreate(
                    email=settings.admin_email,
                    password=settings.admin_password,
                    is_superuser=True,
                    is_verified=True,
                )
            )
            log.info("admin_user_created", email=user.email, id=str(user.id))
        except UserAlreadyExists:
            log.info("admin_user_already_exists", email=settings.admin_email)


if __name__ == "__main__":
    asyncio.run(seed_admin())
