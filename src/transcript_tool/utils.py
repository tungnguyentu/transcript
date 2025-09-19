"""Utility helpers shared across transcript tool components."""

from __future__ import annotations

from typing import Any, Iterable


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp (HH:MM:SS,mmm)."""

    milliseconds_total = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds_total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_whole, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds_whole:02},{milliseconds:03}"


def segments_to_srt(segments: Iterable[dict[str, Any]]) -> str:
    """Convert Whisper segments to SRT formatted subtitle content."""

    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        start = format_timestamp(float(segment.get("start", 0.0)))
        end = format_timestamp(float(segment.get("end", 0.0)))

        lines.append(str(index))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    if not lines:
        return ""

    return "\n".join(lines).strip() + "\n"


__all__ = ["format_timestamp", "segments_to_srt"]
