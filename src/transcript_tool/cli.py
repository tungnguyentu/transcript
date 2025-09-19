"""Command-line interface for video transcription with Whisper."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Callable, Optional

import torch

from .engine import resolve_compute_type, transcribe_with_cache
from .utils import format_timestamp, segments_to_srt


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
        "--segment-length",
        type=int,
        default=60,
        help="Audio segment length in seconds for preprocessing (default: 60)",
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
    segment_length: int = 60,
    progress_callback: Optional[Callable[[float], None]] = None,
    pause_check: Optional[Callable[[], None]] = None,
) -> tuple[pathlib.Path, Optional[pathlib.Path]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    transcript_path = output_path or input_path.with_suffix(".txt")

    if not write_subtitle and subtitle_output_path:
        raise ValueError("Cannot provide subtitle_output_path when subtitles are disabled")

    resolved_device = resolve_device(device)
    compute_type = resolve_compute_type(resolved_device)

    subtitle_path: Optional[pathlib.Path] = None
    if write_subtitle:
        subtitle_path = subtitle_output_path or input_path.with_suffix(".srt")

    return transcribe_with_cache(
        input_path,
        model_name=model,
        device=resolved_device,
        compute_type=compute_type,
        task="transcribe" if keep_source_language else "translate",
        beam_size=beam_size,
        temperature=temperature,
        segment_length=segment_length,
        output_path=transcript_path,
        subtitle_path=subtitle_path,
        progress_callback=progress_callback,
        pause_check=pause_check,
    )


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
        segment_length=args.segment_length,
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
