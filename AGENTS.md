# Repository Guidelines

## Project Structure & Module Organization
Keep executable code in `src/`, grouped by domain (e.g., `src/ingest`, `src/processing`, `src/output`). Shared utilities live in `src/common`. Tests mirror the source hierarchy in `tests/`, using the same package names. Place example transcripts or fixtures in `assets/fixtures`, and long-form documentation in `docs/`. Configuration that needs to ship with the code belongs in `config/`; keep local-only settings under `config/local/` and exclude them from commits.

## Build, Test, and Development Commands
Create an isolated environment before contributing: `python -m venv .venv && source .venv/bin/activate`. Install runtime and tooling dependencies with `pip install -e .[dev]`. Run the full suite using `pytest`; the `--maxfail=1 --disable-warnings -q` flags give fast feedback. Use `make lint` prior to opening a pull request; it chains formatting, type checks, and static analysis. When touching CLI entry points, sanity check with `python -m transcript.cli < sample.json` to confirm end-to-end behaviour.

## Coding Style & Naming Conventions
Adhere to PEP 8 with 4-space indentation. Run `black .` for formatting and `ruff check .` for linting; both are enforced in CI. Modules use snake_case filenames, classes are PascalCase, and functions plus variables remain snake_case. Prefer descriptive names over abbreviations; reserve acronyms for well-known transcript tooling (e.g., ASR, NER). Keep modules under 200 lines by extracting helpers into `src/common` when logic repeats.

## Testing Guidelines
Write pytest tests alongside the code under `tests/<module>/test_<feature>.py`. Use fixtures for filesystem artifacts rather than inline strings. Aim to keep statement coverage above 90% for any touched package; add regression tests when fixing bugs. Integration tests that exercise the end-to-end transcript pipeline live in `tests/integration/` and may use recorded artifacts from `assets/fixtures`.

## Commit & Pull Request Guidelines
Follow Conventional Commits (`feat:`, `fix:`, `chore:`) so automation can infer release notes. Keep commits focused; split logic, refactors, and formatting into separate entries. Pull requests must include a short summary, testing evidence (commands and outcomes), and references to tracked work items. Capture behavioural changes with before/after notes or screenshots when the output format changes. Request review from another agent before merging; no self-merges without explicit approval.

## Environment & Secrets
Never commit API keys or transcript files subject to privacy agreements. Use `.env` for local secrets and document required variables in `docs/environment.md`. If a secret is leaked, rotate it immediately and note the remediation in the pull request.
