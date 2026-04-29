"""
Tests for the bank simulator FastAPI service.
Run with: pytest test_app.py -v
"""
import asyncio
import pytest
import pytest_anyio
import app as bank_app
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=bank_app.app), base_url="http://test")


SETTLE_PAYLOAD = {
    "payout_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "amount_paise": 50000,
    "callback_url": "http://engine/webhooks/bank/",
}


# ---------------------------------------------------------------------------
# Test 1 — seed 0 → success
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_settle_success_outcome():
    bank_app._seed = 0.0  # 0.0 < 0.70 → success
    try:
        async with make_client() as client:
            resp = await client.post("/settle", json=SETTLE_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["outcome_will_be"] == "success"
    finally:
        bank_app._seed = None


# ---------------------------------------------------------------------------
# Test 2 — seed forcing failure
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_settle_failure_outcome():
    bank_app._seed = 0.80  # 0.70 <= 0.80 < 0.90 → failure
    try:
        async with make_client() as client:
            resp = await client.post("/settle", json=SETTLE_PAYLOAD)
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["outcome_will_be"] == "failure"
    finally:
        bank_app._seed = None


# ---------------------------------------------------------------------------
# Test 3 — seed forcing pending → no callback fired
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_settle_pending_no_callback():
    bank_app._seed = 0.95  # >= 0.90 → pending
    try:
        with patch("app._fire_callback", new_callable=AsyncMock) as mock_cb:
            async with make_client() as client:
                resp = await client.post("/settle", json=SETTLE_PAYLOAD)
            assert resp.status_code == 200
            body = resp.json()
            assert body["outcome_will_be"] == "pending"
            # Background task must NOT have been scheduled for pending
            mock_cb.assert_not_called()
    finally:
        bank_app._seed = None


# ---------------------------------------------------------------------------
# Test 4 — success outcome fires callback with correct body
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_settle_success_fires_callback():
    bank_app._seed = 0.0  # → success
    try:
        # Patch _fire_callback at the module level so the ASGI test client is
        # not accidentally mocked by a class-level httpx patch.
        with patch("app._fire_callback", new_callable=AsyncMock) as mock_cb:
            async with make_client() as client:
                resp = await client.post("/settle", json=SETTLE_PAYLOAD)
            assert resp.status_code == 200
            body = resp.json()
            assert body["outcome_will_be"] == "success"

            # BackgroundTasks run inline in the ASGI test transport.
            await asyncio.sleep(0.5)

            mock_cb.assert_called_once_with(
                SETTLE_PAYLOAD["callback_url"],
                SETTLE_PAYLOAD["payout_id"],
                "success",
            )
    finally:
        bank_app._seed = None


# ---------------------------------------------------------------------------
# Test 5 — health endpoint
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_health():
    async with make_client() as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
