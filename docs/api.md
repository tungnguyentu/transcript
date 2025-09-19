# Transcript Tool API Reference

Base URL defaults to `http://127.0.0.1:8000` when running `python run.py`. All responses are JSON unless otherwise noted.

---

## POST /api/transcribe

Start a new transcription job.

### Request
- **Content-Type:** `multipart/form-data`
- **Fields:**
  - `file` *(required)* — Binary upload of the video/audio file.
  - `model` *(optional, default `medium`)* — Whisper model name (`tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3`).
  - `keep_source_language` *(optional)* — Include the form field with any value (e.g., `1`) to keep the transcript in its original language instead of translating to English.
  - `skip_subtitle` *(optional)* — Include the field with any value (e.g., `1`) to skip `.srt` subtitle generation.

### Successful Response
```json
{
  "task_id": "19f3cf6f87a24f7cb7691092eaae7e5f"
}
```
- `task_id` uniquely identifies the background transcription job.

### Error Responses
- `400 Bad Request` with JSON body `{ "detail": "<reason>" }` when the model is invalid or the file is missing.

---

## GET /api/status/{task_id}

Fetch the latest status for a job.

### Path Parameters
- `task_id` — Identifier returned by `/api/transcribe`.

### Successful Response
```json
{
  "task_id": "19f3cf6f87a24f7cb7691092eaae7e5f",
  "status": "processing",
  "progress": 45,
  "message": "Processing...",
  "model": "base",
  "keep_source_language": false,
  "skip_subtitle": false,
  "paused": false,
  "subtitle_ready": false,
  "subtitle_filename": null,
  "subtitle_url": null
}
```

- `status` — One of `queued`, `processing`, `paused`, `completed`, `error`.
- `progress` — Integer percentage (0–100) representing overall progress.
- `message` — Human-readable status description.
- `paused` — Indicates whether the task is paused.
- `subtitle_ready` — `true` when the `.srt` is ready to download.
- `subtitle_filename` — Output filename (same base name as uploaded video) when ready.
- `subtitle_url` — Relative URL for downloading the subtitle once ready (`/api/download/{task_id}`).

### Error Responses
- `404 Not Found` with `{ "detail": "Task not found" }` if the job ID is unknown or already purged after download.

---

## POST /api/pause/{task_id}

Pause an in-progress job.

### Successful Response
```json
{
  "task_id": "19f3cf6f87a24f7cb7691092eaae7e5f",
  "status": "paused",
  "progress": 52,
  "message": "Paused by user",
  "paused": true,
  "subtitle_ready": false,
  "subtitle_filename": null,
  "subtitle_url": null
}
```

### Error Responses
- `400 Bad Request` if the job already completed or failed.
- `404 Not Found` if the job ID is unknown.

---

## POST /api/resume/{task_id}

Resume a paused job.

### Successful Response
```json
{
  "task_id": "19f3cf6f87a24f7cb7691092eaae7e5f",
  "status": "processing",
  "progress": 52,
  "message": "Resuming task",
  "paused": false,
  "subtitle_ready": false,
  "subtitle_filename": null,
  "subtitle_url": null
}
```

### Error Responses
- `400 Bad Request` if the job already completed or failed.
- `404 Not Found` if the job ID is unknown.

---

## GET /api/download/{task_id}

Download the generated subtitle file.

### Successful Response
- **Status:** `200 OK`
- **Headers:**
  - `Content-Type: text/plain`
  - `Content-Disposition: attachment; filename="<video-base>.srt"`
- **Body:** Subtitle content in `.srt` format.

### Error Responses
- `404 Not Found` if the subtitle is not available (task still running, failed, or purged).

---

## Client Integration Notes
- Store the `task_id` from `/api/transcribe` to drive polling and UI recovery after reloads.
- Poll `/api/status/{task_id}` every 1–2 seconds until `status` is `completed` or `error`.
- When `subtitle_ready` is `true`, enable a download control that hits `/api/download/{task_id}`.
- For pause/resume toggles, call `/api/pause/{task_id}` and `/api/resume/{task_id}` based on the current `paused` flag.
- Tasks remain available in memory until the server process restarts. Completed tasks persist so downloads remain accessible; your client should clear stored `task_id` values once the subtitle is retrieved.
- A Celery worker must be running (`python run.py worker --loglevel info`) with access to the shared `TRANSCRIPT_TOOL_WORK_DIR` so the web API can hand off uploads and pick up generated subtitles; configure broker/backends via `TRANSCRIPT_TOOL_BROKER_URL` and `TRANSCRIPT_TOOL_RESULT_BACKEND`.
