"""Celery tasks for transcript processing."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from celery import states
from celery.utils.log import get_task_logger

from .celery_app import celery_app
from .cli import transcribe_media

LOGGER = get_task_logger(__name__)

WORK_ROOT = Path(os.getenv("TRANSCRIPT_TOOL_WORK_DIR", "work")).resolve()
UPLOAD_ROOT = WORK_ROOT / "uploads"
OUTPUT_ROOT = WORK_ROOT / "outputs"
SUBTITLE_ROOT = OUTPUT_ROOT / "subtitles"
TRANSCRIPT_ROOT = OUTPUT_ROOT / "transcripts"

for directory in (UPLOAD_ROOT, OUTPUT_ROOT, SUBTITLE_ROOT, TRANSCRIPT_ROOT):
    directory.mkdir(parents=True, exist_ok=True)


def load_metadata(metadata_path: Path) -> dict:
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    return {}


def write_metadata(metadata_path: Path, data: dict) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@celery_app.task(bind=True)
def transcribe_job(self, payload: dict) -> dict:
    """Run transcription via faster-whisper with progress updates."""

    job_id: str = payload["task_id"]
    metadata_path = Path(payload["metadata_path"])
    meta = load_metadata(metadata_path)

    def update_progress(progress: int, message: str) -> None:
        meta.update(
            {
                "progress": progress,
                "message": message,
            }
        )
        write_metadata(metadata_path, meta)
        self.update_state(
            state="PROGRESS",
            meta={
                "progress": progress,
                "message": message,
                "subtitle_ready": meta.get("subtitle_ready", False),
                "subtitle_filename": meta.get("subtitle_filename"),
            },
        )

    meta.update({
        "status": "processing",
        "progress": 5,
        "message": "Preparing audio",
    })
    write_metadata(metadata_path, meta)
    update_progress(5, "Preparing audio")

    input_path = Path(payload["input_path"])
    transcript_path = Path(payload["transcript_path"])
    subtitle_path_str: Optional[str] = payload.get("subtitle_path")
    subtitle_path = Path(subtitle_path_str) if subtitle_path_str else None
    segment_length = int(payload.get("segment_length", 60))

    def pause_check() -> None:
        while True:
            latest = load_metadata(metadata_path)
            if latest.get("status") == "paused":
                update_progress(latest.get("progress", 0), "Paused")
                time.sleep(1)
            else:
                meta.update(latest)
                break

    try:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        if subtitle_path:
            subtitle_path.parent.mkdir(parents=True, exist_ok=True)

        transcribe_media(
            input_path,
            model=payload["model"],
            output_path=transcript_path,
            keep_source_language=payload.get("keep_source_language", False),
            device=payload.get("device"),
            temperature=payload.get("temperature", 0.0),
            beam_size=payload.get("beam_size", 5),
            verbose=False,
            write_subtitle=subtitle_path is not None,
            subtitle_output_path=subtitle_path,
            segment_length=segment_length,
            progress_callback=lambda ratio: update_progress(
                10 + int(min(max(ratio, 0.0), 1.0) * 70), "Transcribing audio"
            ),
            pause_check=pause_check,
        )

        meta.update(
            {
                "status": "completed",
                "progress": 100,
                "message": "Transcription complete",
                "subtitle_ready": subtitle_path is not None,
                "subtitle_filename": subtitle_path.name if subtitle_path else None,
                "subtitle_path": str(subtitle_path) if subtitle_path else None,
                "transcript_path": str(transcript_path),
            }
        )
        write_metadata(metadata_path, meta)
        return meta
    except Exception as exc:  # noqa: BLE001 - capture any failure for Celery
        LOGGER.exception("Transcription failed for job %s", job_id)
        meta.update(
            {
                "status": "error",
                "progress": 100,
                "message": str(exc),
                "subtitle_ready": False,
            }
        )
        write_metadata(metadata_path, meta)
        self.update_state(state=states.FAILURE, meta=meta)
        raise


__all__ = [
    "transcribe_job",
    "UPLOAD_ROOT",
    "SUBTITLE_ROOT",
    "WORK_ROOT",
    "load_metadata",
    "write_metadata",
]
