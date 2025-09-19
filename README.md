# Transcript Tool

Python-based command-line tool for translating video audio to English text using OpenAI Whisper.

## Features
- Accepts video files in any format supported by FFmpeg.
- Uses faster-whisper for accelerated transcription/translation while keeping Whisper accuracy.
- Saves transcripts as UTF-8 `.txt` files alongside the source video.
- Emits `.srt` subtitle files by default for easy use in players or editing suites.
- Allows optional preservation of the source language transcript.
- Ships with a FastAPI-powered web UI for simple uploads and downloads.

## Quick Start
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies and ensure FFmpeg is on your PATH:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. Make sure a Redis server is available (default: `redis://localhost:6379/0`). On macOS:
   ```bash
   brew install redis
   redis-server
   ```
   Or spin up Docker: `docker run --rm -p 6379:6379 redis`.
3. Transcribe and translate a video to English (produces both `.txt` transcript and `.srt` subtitle files next to the video by default):
   ```bash
   python -m transcript_tool.cli /path/to/video.mp4
   ```
4. To keep the transcript in the original language:
   ```bash
   python -m transcript_tool.cli /path/to/video.mp4 --keep-source-language
   ```
5. To skip subtitle generation or customize its location:
   ```bash
   # Skip the .srt file entirely
   python -m transcript_tool.cli /path/to/video.mp4 --no-subtitle

   # Write the subtitle to a specific path
   python -m transcript_tool.cli /path/to/video.mp4 --subtitle-output /tmp/output.srt
   ```

## Web UI
- Launch the web interface through the helper script (add `--reload` during development if desired):
  ```bash
  python run.py --reload
  ```
- Start the background worker in another terminal (defaults to Redis on `redis://localhost:6379/0`; override with `TRANSCRIPT_TOOL_BROKER_URL`/`TRANSCRIPT_TOOL_RESULT_BACKEND`):
  ```bash
  python run.py worker --loglevel info
  ```
- Open <http://127.0.0.1:8000/> in your browser, upload a video, choose a Whisper model, and click **Transcribe**.
- Track background progress in the page; when finished, click **Download Subtitle** to grab the `.srt` (named after the uploaded video).
- The page remembers in-progress tasks, so refreshing resumes progress updates automatically.
- Use the Pause/Resume button to temporarily halt long transcriptions when you need resources back.

## Tips
- Whisper requires FFmpeg; install via `brew install ffmpeg` (macOS) or your package manager.
- Large models (`large-v3`) give best accuracy but need more VRAM and disk space.
- Use `--device cuda` to force GPU execution when available for faster processing.
- Tune performance with `--segment-length` (audio pre-splitting) to balance speed vs. memory use.
- Configure Celery with `TRANSCRIPT_TOOL_BROKER_URL`/`TRANSCRIPT_TOOL_RESULT_BACKEND` and adjust the shared work directory via `TRANSCRIPT_TOOL_WORK_DIR` if you deploy across machines. Redis is required by default; install the server or point the variables at another supported broker/backend.
