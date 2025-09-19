"""FastAPI-based web UI for the transcript tool."""

from __future__ import annotations

import html
import pathlib
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .cli import transcribe_media

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

OUTPUT_DIR = pathlib.Path("output_subtitles")


@dataclass
class TaskState:
    status: str
    progress: int = 0
    message: Optional[str] = None
    model: str = "medium"
    keep_source_language: bool = False
    skip_subtitle: bool = False
    paused: bool = False
    subtitle_file: Optional[pathlib.Path] = None


@dataclass
class TaskControl:
    pause_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)
    progress_thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.pause_event.set()


TASKS: Dict[str, TaskState] = {}
TASK_LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=2)
TASK_CONTROLS: Dict[str, TaskControl] = {}


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
    message_block = f"<p class=\"message\" id=\"status-message\">{html.escape(message)}</p>" if message else "<p class=\"message\" id=\"status-message\"></p>"
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
            .message {{ color: #d00; font-weight: bold; }}
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


def _update_task(task_id: str, **updates: object) -> None:
    with TASK_LOCK:
        state = TASKS.get(task_id)
        if not state:
            return
        for key, value in updates.items():
            setattr(state, key, value)


def _get_task_and_control(task_id: str) -> tuple[TaskState, TaskControl]:
    with TASK_LOCK:
        state = TASKS.get(task_id)
        control = TASK_CONTROLS.get(task_id)
    if not state or not control:
        raise HTTPException(status_code=404, detail="Task not found")
    return state, control


def _task_payload(task_id: str, state: TaskState) -> dict[str, object]:
    return {
        "task_id": task_id,
        "status": state.status,
        "progress": state.progress,
        "message": state.message,
        "model": state.model,
        "keep_source_language": state.keep_source_language,
        "skip_subtitle": state.skip_subtitle,
        "paused": state.paused,
        "subtitle_ready": state.subtitle_file is not None,
        "subtitle_filename": state.subtitle_file.name if state.subtitle_file else None,
        "subtitle_url": f"/api/download/{task_id}" if state.subtitle_file else None,
    }


def _start_progress_simulation(task_id: str, control: TaskControl) -> None:
    def _simulate() -> None:
        while not control.stop_event.is_set():
            control.pause_event.wait()
            if control.stop_event.is_set():
                break
            with TASK_LOCK:
                state = TASKS.get(task_id)
            if not state:
                break
            if state.status != "processing" or state.paused:
                time.sleep(0.5)
                continue
            next_progress = min(80, state.progress + 5 if state.progress < 80 else state.progress)
            if next_progress > state.progress:
                _update_task(task_id, progress=next_progress, message="Processing...")
            time.sleep(2)

    thread = threading.Thread(target=_simulate, daemon=True)
    control.progress_thread = thread
    thread.start()


def _run_transcription_task(
    *,
    task_id: str,
    input_path: pathlib.Path,
    model: str,
    keep_source_language: bool,
    skip_subtitle: bool,
) -> None:
    _, control = _get_task_and_control(task_id)

    control.pause_event.wait()
    _update_task(
        task_id,
        status="processing",
        progress=10,
        message="Processing transcription",
        paused=False,
    )
    _start_progress_simulation(task_id, control)

    try:
        transcript_path, subtitle_path = transcribe_media(
            input_path,
            model=model,
            keep_source_language=keep_source_language,
            write_subtitle=not skip_subtitle,
        )
        control.pause_event.wait()
        _update_task(task_id, progress=90, message="Finalizing outputs")

        subtitle_file: Optional[pathlib.Path] = None
        if subtitle_path:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            subtitle_file = OUTPUT_DIR / subtitle_path.name
            shutil.copy2(subtitle_path, subtitle_file)

        _update_task(
            task_id,
            status="completed",
            progress=100,
            message="Transcription complete",
            paused=False,
            subtitle_file=subtitle_file,
        )
    except Exception as exc:  # noqa: BLE001 - capture and expose to caller
        _update_task(
            task_id,
            status="error",
            progress=100,
            message=str(exc),
            paused=False,
            subtitle_file=None,
        )
    finally:
        control.stop_event.set()
        try:
            shutil.rmtree(input_path.parent, ignore_errors=True)
        except OSError:
            pass


def _create_task_state(
    *,
    model: str,
    keep_source_language: bool,
    skip_subtitle: bool,
) -> tuple[str, TaskState]:
    task_id = uuid.uuid4().hex
    state = TaskState(
        status="queued",
        progress=0,
        message="Task queued",
        model=model,
        keep_source_language=keep_source_language,
        skip_subtitle=skip_subtitle,
    )
    control = TaskControl()
    with TASK_LOCK:
        TASKS[task_id] = state
        TASK_CONTROLS[task_id] = control
    return task_id, state


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

    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="transcribe-tool-"))
    safe_name = pathlib.Path(file.filename).name or "upload"
    input_path = temp_dir / safe_name

    with input_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)

    file.file.close()

    task_id, _state = _create_task_state(
        model=model,
        keep_source_language=keep_source_language,
        skip_subtitle=skip_subtitle,
    )

    EXECUTOR.submit(
        _run_transcription_task,
        task_id=task_id,
        input_path=input_path,
        model=model,
        keep_source_language=keep_source_language,
        skip_subtitle=skip_subtitle,
    )

    return JSONResponse({"task_id": task_id})


@app.get("/api/status/{task_id}")
async def get_status(task_id: str) -> JSONResponse:
    with TASK_LOCK:
        state = TASKS.get(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="Task not found")

    payload = _task_payload(task_id, state)

    return JSONResponse(payload)


@app.post("/api/pause/{task_id}")
async def pause_task(task_id: str) -> JSONResponse:
    state, control = _get_task_and_control(task_id)
    if state.status in {"completed", "error"}:
        raise HTTPException(status_code=400, detail="Task already finished")
    control.pause_event.clear()
    _update_task(
        task_id,
        status="paused",
        message="Paused by user",
        paused=True,
    )
    with TASK_LOCK:
        refreshed_state = TASKS.get(task_id)
    return JSONResponse(_task_payload(task_id, refreshed_state))


@app.post("/api/resume/{task_id}")
async def resume_task(task_id: str) -> JSONResponse:
    state, control = _get_task_and_control(task_id)
    if state.status in {"completed", "error"}:
        raise HTTPException(status_code=400, detail="Task already finished")
    control.pause_event.set()
    _update_task(
        task_id,
        status="processing",
        message="Resuming task",
        paused=False,
    )
    with TASK_LOCK:
        refreshed_state = TASKS.get(task_id)
    return JSONResponse(_task_payload(task_id, refreshed_state))


@app.get("/api/download/{task_id}")
async def download_subtitle(task_id: str) -> FileResponse:
    state, _control = _get_task_and_control(task_id)
    subtitle_file = state.subtitle_file
    if not subtitle_file or not subtitle_file.exists():
        raise HTTPException(status_code=404, detail="Subtitle not available")
    return FileResponse(
        subtitle_file,
        media_type="text/plain",
        filename=subtitle_file.name,
    )
