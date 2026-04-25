import pytest


def test_celery_app_importable():
    from config.celery import app
    assert app is not None


def test_beat_schedule_has_sweep_stale():
    from django.conf import settings
    assert "sweep-stale" in settings.CELERY_BEAT_SCHEDULE


def test_beat_schedule_has_expire_idempotency():
    from django.conf import settings
    assert "expire-idempotency" in settings.CELERY_BEAT_SCHEDULE


def test_task_acks_late():
    from django.conf import settings
    assert settings.CELERY_TASK_ACKS_LATE is True
