# Transcript Tool

Python-based command-line tool for translating video audio to English text using OpenAI Whisper.

## Features
- Accepts video files in any format supported by FFmpeg.
- Uses Whisper models for high-quality transcription and translation.
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
- Open <http://127.0.0.1:8000/> in your browser, upload a video, choose a Whisper model, and click **Transcribe**.
- Track background progress in the page; when finished, click **Download Subtitle** to grab the `.srt` (named after the uploaded video).
- The page remembers in-progress tasks, so refreshing resumes progress updates automatically.
- Use the Pause/Resume button to temporarily halt long transcriptions when you need resources back.

## Tips
- Whisper requires FFmpeg; install via `brew install ffmpeg` (macOS) or your package manager.
- Large models (`large-v3`) give best accuracy but need more VRAM and disk space.
- Use `--device cuda` to force GPU execution when available for faster processing.
