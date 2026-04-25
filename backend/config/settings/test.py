import os

from .base import *  # noqa: F401, F403

DEBUG = False

_db_url = os.environ.get("DATABASE_URL")
if not _db_url:
    raise RuntimeError("DATABASE_URL must be set for the test suite")

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
