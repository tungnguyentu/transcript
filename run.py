"""Entry point for Transcript Tool web server and Celery worker."""

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

from transcript_tool.celery_app import celery_app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Transcript Tool web server or Celery worker."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="web",
        choices=["web", "worker"],
        help="What to run: web (default) or worker",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (web only, useful during development)",
    )
    parser.add_argument(
        "--loglevel",
        default="info",
        help="Celery worker log level (default: info)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Celery worker concurrency (default: celery chooses)",
    )
    parser.add_argument(
        "--pool",
        help="Celery worker pool implementation (e.g., prefork, solo)",
    )
    return parser.parse_args(argv)


def run_web(args: argparse.Namespace) -> None:
    uvicorn.run(
        "transcript_tool.web:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def run_worker(args: argparse.Namespace) -> None:
    worker_args = [
        "worker",
        f"--loglevel={args.loglevel}",
    ]
    if args.concurrency is not None:
        worker_args.append(f"--concurrency={args.concurrency}")
    if args.pool:
        worker_args.append(f"--pool={args.pool}")
    celery_app.worker_main(worker_args)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.command == "worker":
        run_worker(args)
    else:
        run_web(args)


if __name__ == "__main__":
    main()
