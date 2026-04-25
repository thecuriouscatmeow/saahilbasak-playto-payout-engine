import uuid
from contextlib import contextmanager
import structlog


def get_correlation_id() -> str:
    ctx = structlog.contextvars.get_contextvars()
    return ctx.get("correlation_id", "") or str(uuid.uuid4())


@contextmanager
def bind_correlation_id(correlation_id: str = ""):
    cid = correlation_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    try:
        yield cid
    finally:
        structlog.contextvars.unbind_contextvars("correlation_id")
