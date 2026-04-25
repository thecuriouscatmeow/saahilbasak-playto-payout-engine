from .base import *  # noqa: F401, F403

DEBUG = False
ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(",")  # noqa: F405 — must be set in prod
