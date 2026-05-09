"""JWT authentication helpers for fastapi-users configuration."""

from __future__ import annotations

from app.core.config import settings

JWT_SECRET = settings.secret_key
JWT_ALGORITHM = "HS256"
JWT_LIFETIME_SECONDS = 60 * 60 * 24 * 7  # 7 days
