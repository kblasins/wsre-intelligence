"""Tests for /api/admin endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.review import ReviewQueue

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_health_returns_ok(api_client: AsyncClient) -> None:
    """GET /api/admin/health returns 200 with status field."""
    resp = await api_client.get("/api/admin/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert data["db"] == "ok"
    assert isinstance(data["open_circuit_breakers"], list)
    assert isinstance(data["review_queue_pending"], int)


@pytest.mark.asyncio
async def test_llm_calls_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/llm-calls")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_llm_calls_with_data(api_client: AsyncClient, db_session: AsyncSession) -> None:
    from datetime import UTC, datetime

    from app.models.llm import LLMCall

    call = LLMCall(
        model_id="claude-haiku-4-5-20251001",
        prompt_sha="abc123",
        task_type="triage",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=0.001234,
        success=True,
        called_at=datetime.now(UTC),
    )
    db_session.add(call)
    await db_session.commit()

    resp = await api_client.get("/api/admin/llm-calls?task_type=triage")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    row = next(r for r in data if r["task_type"] == "triage")
    assert row["model_id"] == "claude-haiku-4-5-20251001"
    assert row["cost_usd"] > 0
    assert set(row.keys()) >= {
        "id",
        "model_id",
        "task_type",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "called_at",
    }


@pytest.mark.asyncio
async def test_budget_returns_expected_shape(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert "today_usd" in data
    assert "daily_cap_usd" in data
    assert "budget_pct" in data
    assert "models" in data
    assert isinstance(data["today_calls"], int)
    assert data["today_usd"] >= 0
    assert data["budget_pct"] >= 0


@pytest.mark.asyncio
async def test_budget_non_negative(api_client: AsyncClient) -> None:
    """Budget values are non-negative (other tests may insert LLM call rows)."""
    resp = await api_client.get("/api/admin/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["today_usd"] >= 0.0
    assert data["today_calls"] >= 0
    assert isinstance(data["models"], dict)


@pytest.mark.asyncio
async def test_budget_history_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/budget/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_budget_history_respects_days_param(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/budget/history?days=7")
    assert resp.status_code == 200
    data = resp.json()
    # With empty DB all days have zero spend — list may be empty or have entries with spend=0
    assert isinstance(data, list)
    for row in data:
        assert "day" in row
        assert "spend_usd" in row
        assert "calls" in row
        assert row["spend_usd"] >= 0


@pytest.mark.asyncio
async def test_pipeline_returns_expected_shape(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/pipeline")
    assert resp.status_code == 200
    data = resp.json()
    assert "outbox" in data
    assert "review_queue" in data
    assert "news" in data
    assert set(data["outbox"]) == {"pending", "done", "permanently_failed"}
    assert set(data["review_queue"]) == {"total", "pending_review"}
    assert set(data["news"]) == {"triage_backlog", "extraction_backlog", "body_fetching_backlog"}


@pytest.mark.asyncio
async def test_pipeline_counts_are_non_negative(api_client: AsyncClient) -> None:
    """Pipeline counts are non-negative integers (DB may have seed data from other tests)."""
    resp = await api_client.get("/api/admin/pipeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["outbox"]["pending"] >= 0
    assert data["review_queue"]["total"] >= 0
    assert data["news"]["triage_backlog"] >= 0


@pytest.mark.asyncio
async def test_review_queue_empty(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/review-queue")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Review queue CRUD ───────────────────────────────────────────────────────────


async def _seed_review_item(session: AsyncSession, confidence: int = 2) -> ReviewQueue:
    item = ReviewQueue(
        source_table="transactions",
        source_row_id=42,
        confidence=confidence,
        uncertain_fields=["value_sar", "area_sqm"],
        llm_output={"value_sar": 5_000_000, "area_sqm": 1200},
        model_id="claude-haiku-4-5-20251001",
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@pytest.mark.asyncio
async def test_review_queue_returns_item(api_client: AsyncClient, db_session: AsyncSession) -> None:
    item = await _seed_review_item(db_session)

    resp = await api_client.get("/api/admin/review-queue?pending_only=false")
    assert resp.status_code == 200
    data = resp.json()
    ids = [r["id"] for r in data]
    assert item.id in ids


@pytest.mark.asyncio
async def test_review_queue_item_shape(api_client: AsyncClient, db_session: AsyncSession) -> None:
    await _seed_review_item(db_session, confidence=2)

    resp = await api_client.get("/api/admin/review-queue?pending_only=false")
    assert resp.status_code == 200
    row = resp.json()[0]
    assert "id" in row
    assert "source_table" in row
    assert "confidence" in row
    assert "uncertain_fields" in row
    assert "llm_output" in row
    assert "is_golden" in row
    assert "created_at" in row


@pytest.mark.asyncio
async def test_review_queue_pending_only_hides_reviewed(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    item = await _seed_review_item(db_session)

    # Resolve the item
    patch_resp = await api_client.patch(f"/api/admin/review-queue/{item.id}")
    assert patch_resp.status_code == 200

    # pending_only=true (default) should now return empty
    resp = await api_client.get("/api/admin/review-queue?pending_only=true")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert item.id not in ids


@pytest.mark.asyncio
async def test_resolve_sets_reviewed_at(api_client: AsyncClient, db_session: AsyncSession) -> None:
    item = await _seed_review_item(db_session)

    resp = await api_client.patch(f"/api/admin/review-queue/{item.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reviewed"] is True
    assert data["id"] == item.id


@pytest.mark.asyncio
async def test_resolve_with_golden_flag(api_client: AsyncClient, db_session: AsyncSession) -> None:
    item = await _seed_review_item(db_session)

    resp = await api_client.patch(f"/api/admin/review-queue/{item.id}?is_golden=true")
    assert resp.status_code == 200
    assert resp.json()["is_golden"] is True


@pytest.mark.asyncio
async def test_resolve_unknown_id_returns_404(api_client: AsyncClient) -> None:
    resp = await api_client.patch("/api/admin/review-queue/99999999")
    assert resp.status_code == 404


# ── Jobs / Source Registry ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jobs_returns_list(api_client: AsyncClient) -> None:
    """GET /api/admin/jobs returns a list (empty ok — no seed data in test DB)."""
    resp = await api_client.get("/api/admin/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_jobs_row_shape(api_client: AsyncClient, db_session: AsyncSession) -> None:
    """If rows exist, each has the expected fields."""
    from app.models.ingestion import SourceRegistry

    source = SourceRegistry(
        source_key="test_scraper",
        display_name="Test Scraper",
        source_type="scraper",
    )
    db_session.add(source)
    await db_session.commit()

    resp = await api_client.get("/api/admin/jobs")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["source_key"] == "test_scraper" for r in rows)
    row = next(r for r in rows if r["source_key"] == "test_scraper")
    assert "display_name" in row
    assert "source_type" in row
    assert "is_enabled" in row
    assert "last_success_at" in row
    assert "age_hours" in row
    assert "consecutive_failures" in row
    assert "stale" in row


# ── Source enable/disable ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_toggle_source_returns_404_for_unknown(api_client: AsyncClient) -> None:
    resp = await api_client.patch("/api/admin/sources/nonexistent_source?enabled=false")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_toggle_source_updates_enabled(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.models.ingestion import SourceRegistry

    source = SourceRegistry(
        source_key="toggle_test_src",
        display_name="Toggle Test",
        source_type="scraper",
        is_enabled=True,
    )
    db_session.add(source)
    await db_session.commit()

    resp = await api_client.patch("/api/admin/sources/toggle_test_src?enabled=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_key"] == "toggle_test_src"
    assert data["is_enabled"] is False

    # Verify persisted
    resp2 = await api_client.get("/api/admin/jobs")
    job = next((j for j in resp2.json() if j["source_key"] == "toggle_test_src"), None)
    assert job is not None
    assert job["is_enabled"] is False


# ── Failed outbox ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_outbox_failed_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/outbox/failed")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_outbox_failed_shape(api_client: AsyncClient, db_session: AsyncSession) -> None:
    from app.models.ingestion import RawIngestOutbox

    row = RawIngestOutbox(
        source="aqar",
        raw_uri="s3://test/blob.html",
        content_sha1="a" * 40,
        content_type="text/html",
        structured=0,
        retry_count=3,
        extraction_error="parsing failed",
    )
    db_session.add(row)
    await db_session.commit()

    resp = await api_client.get("/api/admin/outbox/failed")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    item = next(i for i in items if i.get("extraction_error") == "parsing failed")
    assert item["source"] == "aqar"
    assert item["retry_count"] == 3
    assert "fetched_at" in item


# ── Scraper trigger ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_known_scraper_returns_triggered(api_client: AsyncClient) -> None:
    """POST to a known source_key returns {status: triggered}.

    Background task execution is patched — we only verify the HTTP contract.
    """
    from unittest.mock import patch

    with patch("asyncio.ensure_future"):
        resp = await api_client.post("/api/admin/scraper/tadawul/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "triggered"
    assert data["source_key"] == "tadawul"


@pytest.mark.asyncio
async def test_trigger_unknown_source_key_returns_400(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/admin/scraper/nonexistent_xyz/trigger")
    assert resp.status_code == 400
    assert "nonexistent_xyz" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_all_known_scrapers_accept(api_client: AsyncClient) -> None:
    """Every key registered in _SCRAPER_MODULES should return 200."""
    from unittest.mock import patch

    known = [
        "tadawul",
        "rega",
        "aqar",
        "modon",
        "argaam_en",
        "argaam_ar",
        "saudi_gazette",
        "arab_news",
        "etimad",
    ]
    with patch("asyncio.ensure_future"):
        for key in known:
            resp = await api_client.post(f"/api/admin/scraper/{key}/trigger")
            assert resp.status_code == 200, f"Expected 200 for {key}, got {resp.status_code}"


# ── Pipeline step trigger ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_pipeline_unknown_step_returns_400(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/admin/pipeline/nonexistent_step/trigger")
    assert resp.status_code == 400
    assert "nonexistent_step" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_pipeline_known_steps_return_200(api_client: AsyncClient) -> None:
    from unittest.mock import patch

    with patch("asyncio.ensure_future"):
        for step in ["news_body", "news_extract"]:
            resp = await api_client.post(f"/api/admin/pipeline/{step}/trigger")
            assert resp.status_code == 200, f"Expected 200 for {step}"
            assert resp.json()["step"] == step


# ── Rent index CSV import ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rent_index_import_valid_csv(api_client: AsyncClient) -> None:
    csv_content = (
        "district,property_type,period,rent_sar_sqm_annual\n"
        "Al Kharj,warehouse,Q1 2025,320\n"
        "Second Industrial City,warehouse,Q1 2025,295\n"
    )
    resp = await api_client.post(
        "/api/admin/rent-index/import?source=test_import",
        files={"file": ("test.csv", csv_content.encode(), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["inserted"] == 2
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_rent_index_import_missing_column_returns_422(api_client: AsyncClient) -> None:
    csv_content = "district,property_type\nFoo,warehouse\n"
    resp = await api_client.post(
        "/api/admin/rent-index/import",
        files={"file": ("bad.csv", csv_content.encode(), "text/csv")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rent_index_import_invalid_number_skips_row(api_client: AsyncClient) -> None:
    csv_content = (
        "district,property_type,period,rent_sar_sqm_annual\n"
        "Al Kharj,warehouse,Q2 2025,not_a_number\n"
        "Al Kharj,warehouse,Q2 2025,310\n"
    )
    resp = await api_client.post(
        "/api/admin/rent-index/import?source=test_import2",
        files={"file": ("partial.csv", csv_content.encode(), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] >= 1
    assert data["inserted"] >= 1


# ── Circuit breakers ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_breakers_returns_list(api_client: AsyncClient) -> None:
    """GET /api/admin/circuit-breakers returns all known breakers."""
    resp = await api_client.get("/api/admin/circuit-breakers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_circuit_breaker_shape(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/circuit-breakers")
    assert resp.status_code == 200
    row = resp.json()[0]
    assert "name" in row
    assert "state" in row
    assert "fail_counter" in row
    assert "fail_max" in row
    assert row["state"] in ("closed", "open", "half-open", "unknown")


# ── Scheduler ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_returns_list(api_client: AsyncClient) -> None:
    """GET /api/admin/schedule returns a list (empty when scheduler not running in tests)."""
    resp = await api_client.get("/api/admin/schedule")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── POST /api/admin/districts ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_district_alias_success(api_client: AsyncClient, db_session) -> None:
    """POST /api/admin/districts accepts JSON body and returns created alias."""
    payload = {
        "canonical_id": 9001,
        "alias": "Industrial Valley",
        "lang": "en",
        "city": "Riyadh",
    }
    resp = await api_client.post("/api/admin/districts", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["canonical_id"] == 9001
    assert data["alias"] == "Industrial Valley"
    assert data["alias_lang"] == "en"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_district_alias_arabic(api_client: AsyncClient, db_session) -> None:
    """POST /api/admin/districts works with Arabic aliases."""
    payload = {
        "canonical_id": 9002,
        "alias": "وادي الصناعة",
        "lang": "ar",
        "city": "Jeddah",
    }
    resp = await api_client.post("/api/admin/districts", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["alias"] == "وادي الصناعة"
    assert data["alias_lang"] == "ar"


@pytest.mark.asyncio
async def test_admin_districts_get_returns_list(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/admin/districts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
