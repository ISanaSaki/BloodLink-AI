"""Celery application: broker, result backend and the MVP beat schedule (sections 12, 12.1)."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "blood_donation",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Explicit import: autodiscover looks for `<pkg>.tasks` submodules, and this package
    # holds `notification_tasks`, so a worker started without it would register nothing.
    imports=("app.tasks.notification_tasks",),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_default_queue="default",
    task_routes={
        "app.tasks.notification_tasks.dispatch_notification_batch": {"queue": "notifications"},
        "app.tasks.notification_tasks.cancel_pending_notifications": {"queue": "notifications"},
    },
    beat_schedule={
        "check-dispatch-timeout": {
            "task": "app.tasks.notification_tasks.check_dispatch_timeout",
            "schedule": 60.0,
        },
    },
)
