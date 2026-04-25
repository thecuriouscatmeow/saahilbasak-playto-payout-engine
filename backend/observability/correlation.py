import uuid
from contextvars import ContextVar
from contextlib import contextmanager

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return _correlation_id.get() or str(uuid.uuid4())


@contextmanager
def bind_correlation_id(correlation_id: str):
    token = _correlation_id.set(correlation_id or str(uuid.uuid4()))
    try:
        yield
    finally:
        _correlation_id.reset(token)
