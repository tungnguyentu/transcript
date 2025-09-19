"""High-performance transcription engine built on faster-whisper."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from faster_whisper import WhisperModel

from .utils import segments_to_srt


@dataclass
class SubtitleSegment:
    index: int
    start: float
    end: float
    text: str


class ModelCache:
    """Thread-safe cache for faster-whisper models."""

    _lock = threading.Lock()
    _models: dict[tuple[str, str, str], WhisperModel] = {}
    _logger = logging.getLogger(__name__)

    @classmethod
    def get(cls, model_name: str, device: str, compute_type: str) -> WhisperModel:
        key = (model_name, device, compute_type)
        with cls._lock:
            model = cls._models.get(key)
            if model is None:
                fallback_model: Optional[WhisperModel] = None
                try:
                    model = WhisperModel(model_name, device=device, compute_type=compute_type)
                except (RuntimeError, ValueError) as exc:
                    if compute_type != "float32":
                        cls._logger.warning(
                            "Compute type %s unsupported on %s, falling back to float32: %s",
                            compute_type,
                            device,
                            exc,
                        )
                        fallback_model = WhisperModel(
                            model_name, device=device, compute_type="float32"
                        )
                        model = fallback_model
                    else:
                        raise
                cls._models[key] = model
                if fallback_model is not None:
                    cls._models[(model_name, device, "float32")] = fallback_model
        return model


def resolve_compute_type(device: str | None) -> str:
    if device == "cuda":
        return "float16"
    if device == "cpu":
        return "int8"
    # Let faster-whisper decide (e.g., auto, mps)
    return "auto"


def split_audio(input_path: Path, segment_length: int = 60) -> tuple[Path, List[Path]]:
    """Convert audio to 16k mono wav and split into uniform segments."""

    temp_dir = Path(tempfile.mkdtemp(prefix="transcript-audio-"))
    segment_template = temp_dir / "segment_%04d.wav"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "segment",
        "-segment_time",
        str(segment_length),
        "-reset_timestamps",
        "1",
        str(segment_template),
    ]
    subprocess.run(command, check=True)
    segments = sorted(temp_dir.glob("segment_*.wav"))
    if not segments:
        raise RuntimeError("FFmpeg failed to generate audio segments")
    return temp_dir, segments


def assemble_transcript(
    segments: Iterable[SubtitleSegment],
    transcript_path: Path,
    subtitle_path: Optional[Path] = None,
) -> tuple[Path, Optional[Path]]:
    transcript_text = "\n".join(seg.text for seg in segments).strip()
    if not transcript_text:
        raise RuntimeError("Transcription produced no text")
    transcript_path.write_text(transcript_text, encoding="utf-8")

    if subtitle_path:
        srt_content = segments_to_srt(
            [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in segments
            ]
        )
        if not srt_content:
            raise RuntimeError("No subtitle content generated")
        subtitle_path.write_text(srt_content, encoding="utf-8")

    return transcript_path, subtitle_path


def transcribe_with_cache(
    input_path: Path,
    *,
    model_name: str,
    device: str,
    compute_type: str,
    task: str,
    beam_size: int,
    temperature: float,
    segment_length: int,
    output_path: Path,
    subtitle_path: Optional[Path],
    progress_callback: Optional[Callable[[float], None]] = None,
    pause_check: Optional[Callable[[], None]] = None,
) -> tuple[Path, Optional[Path]]:
    temp_dir: Optional[Path] = None
    try:
        temp_dir, audio_segments = split_audio(input_path, segment_length=segment_length)
        model = ModelCache.get(model_name, device, compute_type)

        collected: List[SubtitleSegment] = []
        offset = 0.0
        segment_index = 1
        total_segments = len(audio_segments)

        for processed_count, audio_segment in enumerate(audio_segments, start=1):
            if pause_check:
                pause_check()
            segment_results, _info = model.transcribe(
                str(audio_segment),
                beam_size=beam_size,
                temperature=temperature,
                task=task,
                vad_filter=True,
            )
            last_end = offset
            for result in segment_results:
                text = result.text.strip()
                if not text:
                    continue
                start = offset + float(result.start)
                end = offset + float(result.end)
                collected.append(
                    SubtitleSegment(index=segment_index, start=start, end=end, text=text)
                )
                segment_index += 1
                last_end = max(last_end, end)
            offset = max(last_end, offset + segment_length)

            if progress_callback and total_segments:
                progress_callback(processed_count / total_segments)

        return assemble_transcript(collected, output_path, subtitle_path)
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


__all__ = [
    "transcribe_with_cache",
    "resolve_compute_type",
]
