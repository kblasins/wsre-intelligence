"""Tests for /api/auth and /api/users endpoints.

Users are created via UserManager (no public registration endpoint by design —
accounts are seeded by make seed-admin). Auth is tested against
the /api/auth/login → Bearer JWT → /api/users/me flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

_TEST_EMAIL = "authtest@example.com"
_TEST_PASSWORD = "Secure-Test-Pass-99!"


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_test_user(session: AsyncSession) -> None:
    """Create a test user via UserManager (same code path as seed_admin)."""
    from fastapi_users.exceptions import UserAlreadyExists
    from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

    from app.api.routes.auth import UserCreate, UserManager
    from app.models.auth import User

    user_db = SQLAlchemyUserDatabase(session, User)
    mgr = UserManager(user_db)
    try:
        await mgr.create(
            UserCreate(
                email=_TEST_EMAIL,
                password=_TEST_PASSWORD,
                is_superuser=False,
            )
        )
        await session.commit()
    except UserAlreadyExists:
        pass


async def _login(client: AsyncClient, email: str, password: str) -> str | None:
    resp = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    return None


# ── Login ──────────────────────────────────────────────────────────────────────


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_returns_bearer_token(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_test_user(db_session)

        resp = await api_client.post(
            "/api/auth/login",
            data={"username": _TEST_EMAIL, "password": _TEST_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_400(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_test_user(db_session)

        resp = await api_client.post(
            "/api/auth/login",
            data={"username": _TEST_EMAIL, "password": "WrongPassword!999"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_400(self, api_client: AsyncClient) -> None:
        resp = await api_client.post(
            "/api/auth/login",
            data={"username": "nobody@nowhere.com", "password": "whatever"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 400


# ── /api/users/me ──────────────────────────────────────────────────────────────


class TestUsersMe:
    @pytest.mark.asyncio
    async def test_me_with_valid_token_returns_user(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_test_user(db_session)
        token = await _login(api_client, _TEST_EMAIL, _TEST_PASSWORD)
        assert token is not None, "Login failed — check user creation"

        resp = await api_client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == _TEST_EMAIL
        assert "id" in data
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, api_client: AsyncClient) -> None:
        resp = await api_client.get("/api/users/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_garbage_token_returns_401(self, api_client: AsyncClient) -> None:
        resp = await api_client.get(
            "/api/users/me",
            headers={"Authorization": "Bearer totally-fake-jwt-token"},
        )
        assert resp.status_code == 401


# ── Logout ─────────────────────────────────────────────────────────────────────


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_with_valid_token_returns_200(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_test_user(db_session)
        token = await _login(api_client, _TEST_EMAIL, _TEST_PASSWORD)
        assert token is not None

        resp = await api_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_logout_without_token_returns_401(self, api_client: AsyncClient) -> None:
        resp = await api_client.post("/api/auth/logout")
        assert resp.status_code == 401


# ── Protected route gate ────────────────────────────────────────────────────────


class TestProtectedRoutes:
    """Verify that auth-protected routes reject unauthenticated requests."""

    @pytest.mark.asyncio
    async def test_briefs_latest_requires_auth(self, api_client: AsyncClient) -> None:
        resp = await api_client.get("/api/briefs/latest")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_briefs_list_requires_auth(self, api_client: AsyncClient) -> None:
        resp = await api_client.get("/api/briefs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_briefs_trigger_requires_auth(self, api_client: AsyncClient) -> None:
        resp = await api_client.post("/api/briefs/trigger")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_public_routes_dont_require_auth(self, api_client: AsyncClient) -> None:
        """Market data endpoints are public (no auth required)."""
        resp = await api_client.get("/api/stats")
        assert resp.status_code == 200

        resp = await api_client.get("/api/news?limit=1")
        assert resp.status_code == 200

        resp = await api_client.get("/api/tenders?limit=1")
        assert resp.status_code == 200
