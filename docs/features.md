# Transcript Tool Features

## Core Capabilities
- Generates text transcripts for uploaded videos using faster-whisper under the hood (keeping Whisper accuracy with higher throughput).
- Produces `.srt` subtitle files that inherit the uploaded video's base filename.
- Supports Whisper model selection (`tiny` through `large-v3`) and optional source-language preservation.
- Allows subtitle generation to be skipped or written to a custom path when using the CLI.
- Orchestrates background processing via Celery so the web UI remains responsive and can scale across workers (launch via `python run.py worker`).
- Ships with Redis-backed queues by default (configure other backends via `TRANSCRIPT_TOOL_BROKER_URL` / `TRANSCRIPT_TOOL_RESULT_BACKEND`).

## Command-Line Interface
- Entry point: `python -m transcript_tool.cli <video>`
- Key flags: `--model`, `--keep-source-language`, `--no-subtitle`, `--subtitle-output`, `--temperature`, `--beam-size`, `--device`, `--segment-length`, `--verbose`.
- Persists text transcripts alongside the input or at a specified `--output` path.

## Web Interface
- Served via `python run.py [--reload --host --port]` (FastAPI + Uvicorn).
- Upload form lets users submit a video, choose a Whisper model, keep the source language, or skip subtitle creation.
- Background task queue powered by Celery with progress bar, pause/resume control, and status polling every 2 seconds.
- Browser remembers the current task ID so progress resumes after page reloads.
- Subtitles are written to `output_subtitles/` for quick download and reuse across UIs.
- Subtitle download button activates once processing completes, delivering the `.srt` file directly from the server.
- Subtitles are stored under `output_subtitles/` using the original video filename for easy retrieval.

## Operational Notes
- Requires FFmpeg availability and Whisper-compatible hardware/software (GPU optional).
- Long-running tasks can be paused to free compute and resumed later without re-uploading.
- Temporary upload directories are cleaned automatically after processing to avoid disk growth.
