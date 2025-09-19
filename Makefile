.PHONY: install lint format transcribe

install:
	python -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

format:
	. .venv/bin/activate && black src

lint:
	. .venv/bin/activate && ruff check src

transcribe:
	. .venv/bin/activate && python -m transcript_tool.cli --help
