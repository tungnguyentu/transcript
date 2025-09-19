"""Celery application factory for transcript tool."""

from __future__ import annotations

import os

from celery import Celery

BROKER_URL = os.getenv("TRANSCRIPT_TOOL_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("TRANSCRIPT_TOOL_RESULT_BACKEND", BROKER_URL)

celery_app = Celery("transcript_tool", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    imports=("transcript_tool.tasks",),
)

# Ensure auto-discovery for tasks when the worker starts with this module.
celery_app.autodiscover_tasks(packages=["transcript_tool"])

# Provide canonical attribute `celery` for `celery -A transcript_tool.celery_app` usage.
celery = celery_app

__all__ = ["celery_app"]
