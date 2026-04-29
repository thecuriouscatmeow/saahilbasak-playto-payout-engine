import asyncio
import os
import random
from contextlib import asynccontextmanager

import httpx
from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel

# Overridable for tests: set to a float in [0,1) to fix the outcome roll
_seed: float | None = None


def _roll_outcome() -> str:
    r = _seed if _seed is not None else random.random()
    if r < 0.70:
        return "success"
    if r < 0.90:
        return "failure"
    return "pending"


ENGINE_WEBHOOK_URL = os.getenv("ENGINE_WEBHOOK_URL", "")


class SettleRequest(BaseModel):
    payout_id: str
    amount_paise: int
    callback_url: str = ""


class SettleResponse(BaseModel):
    accepted: bool
    outcome_will_be: str


ENGINE_WEBHOOK_SECRET = os.getenv("ENGINE_WEBHOOK_SECRET", "")


async def _fire_callback(callback_url: str, payout_id: str, outcome: str) -> None:
    """Delayed background callback to the payout engine webhook."""
    await asyncio.sleep(random.uniform(0.1, 0.4))
    headers = {}
    if ENGINE_WEBHOOK_SECRET:
        headers["Authorization"] = f"Bearer {ENGINE_WEBHOOK_SECRET}"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json={"payout_id": payout_id, "outcome": outcome},
                headers=headers,
                timeout=10.0,
            )
    except Exception:
        pass


app = FastAPI(title="Bank Simulator", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/settle", response_model=SettleResponse)
async def settle(body: SettleRequest, background_tasks: BackgroundTasks) -> SettleResponse:
    outcome = _roll_outcome()

    # Resolve callback URL: prefer caller-supplied, fall back to env
    cb_url = body.callback_url or ENGINE_WEBHOOK_URL

    # Only fire callback for success/failure; pending means sweeper will retry
    if outcome != "pending" and cb_url:
        background_tasks.add_task(_fire_callback, cb_url, body.payout_id, outcome)

    return SettleResponse(accepted=True, outcome_will_be=outcome)
