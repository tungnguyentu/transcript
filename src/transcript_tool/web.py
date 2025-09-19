"""FastAPI-based web UI for the transcript tool with Celery background jobs."""

from __future__ import annotations

import html
import os
import uuid
from pathlib import Path
from typing import Optional

from celery import states
from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .tasks import (
    SUBTITLE_ROOT,
    UPLOAD_ROOT,
    load_metadata,
    transcribe_job,
    write_metadata,
)

WHISPER_MODELS = [
    "tiny",
    "base",
    "small",
    "medium",
    "large",
    "large-v2",
    "large-v3",
]

app = FastAPI(title="Transcript Tool Web UI")


def job_paths(task_id: str, original_filename: Optional[str] = None) -> dict[str, Path]:
    job_dir = UPLOAD_ROOT / task_id
    metadata_path = job_dir / "metadata.json"
    upload_path = None
    if original_filename is not None:
        upload_path = job_dir / original_filename
    subtitle_dir = SUBTITLE_ROOT / task_id
    return {
        "job_dir": job_dir,
        "metadata_path": metadata_path,
        "upload_path": upload_path,
        "subtitle_dir": subtitle_dir,
    }


def _render_form(
    *,
    message: Optional[str] = None,
    selected_model: str = "medium",
    keep_source_language_checked: bool = False,
    skip_subtitle_checked: bool = False,
) -> HTMLResponse:
    options_html = "\n".join(
        (
            f'<option value="{html.escape(model)}"'
            f" {'selected' if model == selected_model else ''}>{html.escape(model)}</option>"
        ).replace("  ", " ")
        for model in WHISPER_MODELS
    )
    message_block = (
        f"<p class=\"message\" id=\"status-message\">{html.escape(message)}</p>"
        if message
        else "<p class=\"message\" id=\"status-message\"></p>"
    )
    body = f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <title>Transcript Tool Web UI</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 2rem; }}
            form {{ display: grid; gap: 0.75rem; max-width: 28rem; }}
            fieldset {{ border: 1px solid #ccc; padding: 1rem; }}
            label {{ display: block; font-weight: bold; margin-bottom: 0.25rem; }}
            input[type="file"] {{ padding: 0.5rem 0; }}
            .result {{ margin-top: 2rem; }}
            .message {{ color: #d00; font-weight: bold; min-height: 1.2rem; }}
            progress {{ width: 100%; height: 1.5rem; }}
            .status-container {{ max-width: 28rem; margin-top: 1rem; }}
            .download-container {{ margin-top: 1rem; }}
            button[disabled] {{ opacity: 0.6; cursor: not-allowed; }}
        </style>
    </head>
    <body>
        <h1>Transcript Tool Web UI</h1>
        {message_block}
        <form id=\"upload-form\" enctype=\"multipart/form-data\">
            <label for=\"file\">Video file</label>
            <input id=\"file\" name=\"file\" type=\"file\" accept=\"video/*\" required />
            <label for=\"model\">Whisper model</label>
            <select id=\"model\" name=\"model\">{options_html}</select>
            <label><input type=\"checkbox\" name=\"keep_source_language\" value=\"1\" {'checked' if keep_source_language_checked else ''} /> Keep source language</label>
            <label><input type=\"checkbox\" name=\"skip_subtitle\" value=\"1\" {'checked' if skip_subtitle_checked else ''} /> Skip subtitle file</label>
            <button type=\"submit\">Transcribe</button>
        </form>
        <div class=\"status-container\">
            <progress id=\"progress\" value=\"0\" max=\"100\"></progress>
            <p id=\"status-detail\"></p>
            <button type=\"button\" id=\"pause-btn\" disabled>Pause</button>
        </div>
        <div class=\"download-container\">
            <button type=\"button\" id=\"download-btn\" disabled>Download Subtitle</button>
            <p id=\"download-filename\"></p>
        </div>
        <script>
        (() => {{
            const form = document.getElementById('upload-form');
            const progressBar = document.getElementById('progress');
            const statusMessage = document.getElementById('status-message');
            const statusDetail = document.getElementById('status-detail');
            const pauseBtn = document.getElementById('pause-btn');
            const downloadBtn = document.getElementById('download-btn');
            const downloadFilename = document.getElementById('download-filename');

            const TASK_STORAGE_KEY = 'transcript-tool-task-id';

            let pollHandle = null;
            let currentTaskId = null;
            let isPaused = false;
            let subtitleUrl = null;

            const updateDownloadState = (data) => {{
                if (data.subtitle_ready) {{
                    subtitleUrl = data.subtitle_url;
                    downloadBtn.disabled = false;
                    downloadFilename.textContent = data.subtitle_filename || '';
                }} else {{
                    subtitleUrl = null;
                    downloadBtn.disabled = true;
                    downloadFilename.textContent = '';
                }}
            }};

            const saveTaskId = (taskId) => {{
                currentTaskId = taskId;
                try {{
                    localStorage.setItem(TASK_STORAGE_KEY, taskId);
                }} catch (_err) {{}}
            }};

            const clearTaskId = () => {{
                currentTaskId = null;
                try {{
                    localStorage.removeItem(TASK_STORAGE_KEY);
                }} catch (_err) {{}}
            }};

            const applyStatusToControls = (status, paused) => {{
                if (status === 'completed' || status === 'error') {{
                    pauseBtn.disabled = true;
                    pauseBtn.textContent = 'Pause';
                    currentTaskId = null;
                    isPaused = false;
                }} else if (status === 'paused' || paused) {{
                    pauseBtn.disabled = false;
                    pauseBtn.textContent = 'Resume';
                    isPaused = true;
                }} else {{
                    pauseBtn.disabled = !currentTaskId;
                    pauseBtn.textContent = 'Pause';
                    isPaused = false;
                }}
            }};

            const pollStatus = async (taskId) => {{
                try {{
                    const response = await fetch(`/api/status/${{taskId}}`);
                    if (response.status === 404) {{
                        clearTaskId();
                        pauseBtn.disabled = true;
                        downloadBtn.disabled = true;
                        downloadFilename.textContent = '';
                        statusMessage.textContent = 'Task not found.';
                        statusDetail.textContent = '';
                        if (pollHandle) {{
                            clearInterval(pollHandle);
                            pollHandle = null;
                        }}
                        return;
                    }}
                    if (!response.ok) {{
                        throw new Error('Failed to fetch status');
                    }}
                    const data = await response.json();
                    progressBar.value = data.progress ?? 0;
                    statusDetail.textContent = data.message || data.status;
                    applyStatusToControls(data.status, data.paused);
                    updateDownloadState(data);
                    if (data.status === 'completed') {{
                        statusMessage.textContent = 'Transcription complete!';
                        clearTaskId();
                        clearInterval(pollHandle);
                        pollHandle = null;
                    }} else if (data.status === 'error') {{
                        statusMessage.textContent = data.message || 'An error occurred.';
                        clearTaskId();
                        clearInterval(pollHandle);
                        pollHandle = null;
                    }} else {{
                        statusMessage.textContent = (data.status === 'paused' || data.paused) ? 'Paused' : 'Processing...';
                    }}
                }} catch (error) {{
                    statusMessage.textContent = error.message;
                    if (pollHandle) {{
                        clearInterval(pollHandle);
                        pollHandle = null;
                    }}
                }}
            }};

            form.addEventListener('submit', async (event) => {{
                event.preventDefault();
                const formData = new FormData(form);
                progressBar.value = 0;
                statusMessage.textContent = 'Uploading...';
                statusDetail.textContent = '';
                pauseBtn.disabled = true;
                pauseBtn.textContent = 'Pause';
                downloadBtn.disabled = true;
                downloadFilename.textContent = '';
                if (pollHandle) {{
                    clearInterval(pollHandle);
                    pollHandle = null;
                }}

                try {{
                    const response = await fetch('/api/transcribe', {{
                        method: 'POST',
                        body: formData,
                    }});

                    if (!response.ok) {{
                        const errorText = await response.text();
                        throw new Error(errorText || 'Failed to start transcription');
                    }}

                    const data = await response.json();
                    const taskId = data.task_id;
                    saveTaskId(taskId);
                    statusMessage.textContent = 'Task started...';
                    pauseBtn.disabled = false;
                    pauseBtn.textContent = 'Pause';
                    isPaused = false;
                    updateDownloadState({{ subtitle_ready: false }});
                    pollStatus(taskId);
                    pollHandle = setInterval(() => pollStatus(taskId), 2000);
                }} catch (error) {{
                    statusMessage.textContent = error.message;
                }}
            }});

            downloadBtn.addEventListener('click', () => {{
                if (!subtitleUrl) {{
                    return;
                }}
                window.location.href = subtitleUrl;
            }});

            pauseBtn.addEventListener('click', async () => {{
                if (!currentTaskId) {{
                    return;
                }}
                const endpoint = isPaused ? `/api/resume/${{currentTaskId}}` : `/api/pause/${{currentTaskId}}`;
                try {{
                    const response = await fetch(endpoint, {{ method: 'POST' }});
                    if (!response.ok) {{
                        const errorText = await response.text();
                        throw new Error(errorText || 'Failed to update task');
                    }}
                    const data = await response.json();
                    statusDetail.textContent = data.message || data.status;
                    statusMessage.textContent = data.status === 'paused' ? 'Paused' : 'Processing...';
                    applyStatusToControls(data.status, data.paused);
                    updateDownloadState(data);
                }} catch (error) {{
                    statusMessage.textContent = error.message;
                }}
            }});

            const resumeStoredTask = () => {{
                let storedId = null;
                try {{
                    storedId = localStorage.getItem(TASK_STORAGE_KEY);
                }} catch (_err) {{}}
                if (!storedId) {{
                    return;
                }}
                saveTaskId(storedId);
                pauseBtn.disabled = false;
                statusMessage.textContent = 'Restoring in-progress transcription...';
                pollStatus(storedId);
                pollHandle = setInterval(() => pollStatus(storedId), 2000);
            }};

            resumeStoredTask();
        }})();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=body)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return _render_form()


def _status_from_celery(result: AsyncResult, meta: dict) -> dict:
    celery_state = result.state
    status = meta.get("status", "queued")
    paused = status == "paused"

    if celery_state == states.PENDING:
        status = status or "queued"
    elif celery_state in {states.STARTED, "PROGRESS", states.RECEIVED}:
        if not paused:
            status = "processing"
    elif celery_state == states.SUCCESS:
        status = "completed"
    elif celery_state == states.FAILURE:
        status = "error"

    progress = int(meta.get("progress", 0))
    message = meta.get("message", "")
    if celery_state == states.FAILURE and result.info:
        message = str(result.info)

    subtitle_ready = bool(meta.get("subtitle_ready", False))
    subtitle_filename = meta.get("subtitle_filename")

    return {
        "status": status,
        "progress": progress,
        "message": message,
        "paused": paused,
        "subtitle_ready": subtitle_ready,
        "subtitle_filename": subtitle_filename,
    }


def _build_payload(
    task_id: str,
    metadata_path: Path,
    meta: dict,
    file_path: Path,
    subtitle_path: Optional[Path],
    segment_length: int,
    model: str,
) -> dict:
    return {
        "task_id": task_id,
        "metadata_path": str(metadata_path),
        "input_path": str(file_path),
        "model": model,
        "keep_source_language": meta.get("keep_source_language", False),
        "device": meta.get("device"),
        "temperature": meta.get("temperature", 0.0),
        "beam_size": meta.get("beam_size", 5),
        "transcript_path": str(file_path.with_suffix(".txt")),
        "subtitle_path": str(subtitle_path) if subtitle_path else None,
        "segment_length": segment_length,
    }
def _segment_length() -> int:
    return int(os.getenv("TRANSCRIPT_TOOL_SEGMENT_LENGTH", "60"))


def _serialize_status(task_id: str, meta: dict) -> dict:
    result = transcribe_job.AsyncResult(task_id)
    status_payload = _status_from_celery(result, meta)
    subtitle_ready = status_payload["subtitle_ready"]
    subtitle_url = f"/api/download/{task_id}" if subtitle_ready else None

    return {
        "task_id": task_id,
        **status_payload,
        "subtitle_url": subtitle_url,
        "model": meta.get("model"),
        "keep_source_language": meta.get("keep_source_language", False),
        "skip_subtitle": meta.get("skip_subtitle", False),
    }


def _load_meta_or_404(task_id: str) -> tuple[dict, Path]:
    paths = job_paths(task_id)
    meta = load_metadata(paths["metadata_path"])
    if not meta:
        raise HTTPException(status_code=404, detail="Task not found")
    return meta, paths["metadata_path"]


@app.post("/api/transcribe")
async def queue_transcription(
    file: UploadFile = File(...),
    model: str = Form("medium"),
    keep_source_language: bool = Form(False),
    skip_subtitle: bool = Form(False),
) -> JSONResponse:
    if model not in WHISPER_MODELS:
        raise HTTPException(status_code=400, detail="Unknown model requested")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name")

    task_id = uuid.uuid4().hex
    paths = job_paths(task_id, file.filename)
    paths["job_dir"].mkdir(parents=True, exist_ok=True)

    upload_path = paths["upload_path"]
    assert upload_path is not None
    with upload_path.open("wb") as destination:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            destination.write(chunk)

    subtitle_path = None
    if not skip_subtitle:
        subtitle_dir = paths["subtitle_dir"]
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = subtitle_dir / Path(file.filename).with_suffix(".srt")

    segment_length = _segment_length()

    meta = {
        "status": "queued",
        "progress": 0,
        "message": "Task queued",
        "model": model,
        "keep_source_language": bool(keep_source_language),
        "skip_subtitle": bool(skip_subtitle),
        "subtitle_ready": False,
        "subtitle_filename": Path(file.filename).with_suffix(".srt").name if not skip_subtitle else None,
        "original_filename": file.filename,
        "device": None,
        "temperature": 0.0,
        "beam_size": 5,
        "segment_length": segment_length,
    }
    write_metadata(paths["metadata_path"], meta)

    payload = _build_payload(
        task_id,
        paths["metadata_path"],
        meta,
        upload_path,
        subtitle_path,
        segment_length,
        model,
    )

    transcribe_job.apply_async(args=[payload], task_id=task_id)

    return JSONResponse({"task_id": task_id})


@app.get("/api/status/{task_id}")
async def get_status(task_id: str) -> JSONResponse:
    meta, _metadata_path = _load_meta_or_404(task_id)
    response = _serialize_status(task_id, meta)
    return JSONResponse(response)


@app.post("/api/pause/{task_id}")
async def pause_task(task_id: str) -> JSONResponse:
    meta, metadata_path = _load_meta_or_404(task_id)
    if meta.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Task already finished")
    meta.update({"status": "paused", "message": "Paused by user"})
    write_metadata(metadata_path, meta)
    return JSONResponse(_serialize_status(task_id, meta))


@app.post("/api/resume/{task_id}")
async def resume_task(task_id: str) -> JSONResponse:
    meta, metadata_path = _load_meta_or_404(task_id)
    if meta.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Task already finished")
    meta.update({"status": "processing", "message": "Resuming task"})
    write_metadata(metadata_path, meta)
    return JSONResponse(_serialize_status(task_id, meta))


@app.get("/api/download/{task_id}")
async def download_subtitle(task_id: str) -> FileResponse:
    meta, _metadata_path = _load_meta_or_404(task_id)
    subtitle_path = meta.get("subtitle_path")
    if not subtitle_path:
        raise HTTPException(status_code=404, detail="Subtitle not available")
    path_obj = Path(subtitle_path)
    if not path_obj.exists():
        raise HTTPException(status_code=404, detail="Subtitle file missing")
    return FileResponse(
        path_obj,
        media_type="text/plain",
        filename=meta.get("subtitle_filename", path_obj.name),
    )
