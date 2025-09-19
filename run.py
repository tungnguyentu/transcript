"""Run the Transcript Tool web UI via Uvicorn."""

from __future__ import annotations

import argparse
import pathlib
import sys

import uvicorn


def _ensure_src_on_path() -> None:
    project_root = pathlib.Path(__file__).resolve().parent
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


_ensure_src_on_path()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Transcript Tool web server.")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (useful during development)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(
        "transcript_tool.web:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
