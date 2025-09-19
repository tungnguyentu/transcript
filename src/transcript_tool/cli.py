"""Command-line interface for video transcription with Whisper."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any, Callable, Iterable, Optional

import torch
import whisper


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe a video file to English using OpenAI Whisper."
    )
    parser.add_argument("input", type=pathlib.Path, help="Path to the input video file")
    parser.add_argument(
        "--model",
        default="medium",
        choices=[
            "tiny",
            "base",
            "small",
            "medium",
            "large",
            "large-v2",
            "large-v3",
        ],
        help="Whisper model size to use (default: medium)",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="Optional path for the transcript (defaults next to input with .txt)",
    )
    parser.add_argument(
        "--keep-source-language",
        action="store_true",
        help="Transcribe without translating to English",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda"],
        help="Select PyTorch device (default: auto-detect)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for Whisper (higher = more creative, default 0.0)",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="Beam search size; higher improves accuracy at cost of speed",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show word-level timestamps and diagnostics while transcribing",
    )
    parser.add_argument(
        "--no-subtitle",
        action="store_true",
        help="Skip writing an .srt subtitle file",
    )
    parser.add_argument(
        "--subtitle-output",
        type=pathlib.Path,
        help="Optional path for the generated .srt subtitle file",
    )
    return parser.parse_args(argv)


def resolve_device(device_flag: Optional[str]) -> str:
    if device_flag:
        return device_flag
    return "cuda" if torch.cuda.is_available() else "cpu"


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

    # Ensure file ends with a newline to satisfy most players.
    return "\n".join(lines).strip() + "\n"


def transcribe_media(
    input_path: pathlib.Path,
    *,
    model: str = "medium",
    output_path: Optional[pathlib.Path] = None,
    keep_source_language: bool = False,
    device: Optional[str] = None,
    temperature: float = 0.0,
    beam_size: int = 5,
    verbose: bool = False,
    write_subtitle: bool = True,
    subtitle_output_path: Optional[pathlib.Path] = None,
    model_loader: Callable[[str, str], Any] = whisper.load_model,
) -> tuple[pathlib.Path, Optional[pathlib.Path]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    transcript_path = output_path or input_path.with_suffix(".txt")

    if not write_subtitle and subtitle_output_path:
        raise ValueError("Cannot provide subtitle_output_path when subtitles are disabled")

    resolved_device = resolve_device(device)
    model_instance = model_loader(model, device=resolved_device)

    task = "transcribe" if keep_source_language else "translate"

    result = model_instance.transcribe(
        str(input_path),
        temperature=temperature,
        beam_size=beam_size,
        verbose=verbose,
        task=task,
    )

    transcript_text = result.get("text", "").strip()
    if not transcript_text:
        raise RuntimeError("Whisper returned an empty transcript")

    transcript_path.write_text(transcript_text, encoding="utf-8")

    subtitle_path: Optional[pathlib.Path] = None
    if write_subtitle:
        subtitle_path = subtitle_output_path or input_path.with_suffix(".srt")
        segments = result.get("segments", [])
        subtitle_content = segments_to_srt(segments)
        if not subtitle_content:
            raise RuntimeError("Whisper returned no segments for subtitle generation")
        subtitle_path.write_text(subtitle_content, encoding="utf-8")

    return transcript_path, subtitle_path


def transcribe_video(
    args: argparse.Namespace,
) -> tuple[pathlib.Path, Optional[pathlib.Path]]:
    return transcribe_media(
        args.input,
        model=args.model,
        output_path=args.output,
        keep_source_language=args.keep_source_language,
        device=args.device,
        temperature=args.temperature,
        beam_size=args.beam_size,
        verbose=args.verbose,
        write_subtitle=not args.no_subtitle,
        subtitle_output_path=args.subtitle_output,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        transcript_path, subtitle_path = transcribe_video(args)
    except Exception as exc:  # noqa: BLE001 - surface all errors to CLI
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Transcript saved to {transcript_path}")
    if subtitle_path:
        print(f"Subtitle saved to {subtitle_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
