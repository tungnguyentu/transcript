import json
from pathlib import Path
from types import SimpleNamespace

from celery import states
from fastapi.testclient import TestClient

from transcript_tool import tasks, web


class FakeResult:
    def __init__(self, state=states.PENDING, info=None):
        self.state = state
        self.info = info


def setup_paths(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    subtitle_root = tmp_path / "subtitles"
    upload_root.mkdir(parents=True)
    subtitle_root.mkdir(parents=True)

    monkeypatch.setattr(tasks, "UPLOAD_ROOT", upload_root, raising=False)
    monkeypatch.setattr(tasks, "SUBTITLE_ROOT", subtitle_root, raising=False)
    monkeypatch.setattr(web, "UPLOAD_ROOT", upload_root, raising=False)
    monkeypatch.setattr(web, "SUBTITLE_ROOT", subtitle_root, raising=False)

    return upload_root, subtitle_root


def test_index_renders_form():
    client = TestClient(web.app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Transcript Tool Web UI" in response.text
    assert "id=\"upload-form\"" in response.text


def test_transcribe_endpoint(monkeypatch, tmp_path):
    upload_root, subtitle_root = setup_paths(monkeypatch, tmp_path)
    client = TestClient(web.app)

    fake_results = {}

    def fake_apply_async(args=None, kwargs=None, task_id=None):
        payload = args[0]

        meta = json.loads(Path(payload["metadata_path"]).read_text(encoding="utf-8"))
        transcript_path = Path(payload["transcript_path"])
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text("hello world", encoding="utf-8")

        subtitle_path_str = payload.get("subtitle_path")
        if subtitle_path_str:
            subtitle_path = Path(subtitle_path_str)
            subtitle_path.parent.mkdir(parents=True, exist_ok=True)
            subtitle_path.write_text("subtitle content", encoding="utf-8")
            meta.update(
                {
                    "subtitle_path": str(subtitle_path),
                    "subtitle_filename": subtitle_path.name,
                    "subtitle_ready": True,
                }
            )

        meta.update(
            {
                "status": "completed",
                "progress": 100,
                "message": "Transcription complete",
                "transcript_path": str(transcript_path),
            }
        )
        Path(payload["metadata_path"]).write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        fake_results[task_id] = FakeResult(state=states.SUCCESS, info=meta)
        return SimpleNamespace(id=task_id)

    def fake_async_result(task_id):
        return fake_results.get(task_id, FakeResult())

    monkeypatch.setattr(web.transcribe_job, "apply_async", fake_apply_async)
    monkeypatch.setattr(web.transcribe_job, "AsyncResult", fake_async_result)

    files = {"file": ("sample.mp4", b"fake data", "video/mp4")}
    data = {"model": "base"}

    enqueue_response = client.post("/api/transcribe", data=data, files=files)
    assert enqueue_response.status_code == 200
    task_id = enqueue_response.json()["task_id"]

    status_response = client.get(f"/api/status/{task_id}")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "completed"
    assert payload["subtitle_ready"] is True
    assert payload["subtitle_filename"] == "sample.srt"
    assert payload["subtitle_url"] == f"/api/download/{task_id}"

    download_response = client.get(payload["subtitle_url"])
    assert download_response.status_code == 200
    assert download_response.text == "subtitle content"
    assert "sample.srt" in download_response.headers["content-disposition"]


def test_pause_and_resume_controls(monkeypatch, tmp_path):
    upload_root, subtitle_root = setup_paths(monkeypatch, tmp_path)
    client = TestClient(web.app)

    task_id = "dummy"
    job_dir = upload_root / task_id
    job_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = job_dir / "metadata.json"
    metadata = {
        "status": "processing",
        "progress": 30,
        "message": "Processing",
        "model": "base",
        "keep_source_language": False,
        "skip_subtitle": False,
        "subtitle_ready": False,
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    fake_results = {
        task_id: FakeResult(state=states.STARTED, info=metadata),
    }

    monkeypatch.setattr(web.transcribe_job, "AsyncResult", lambda tid: fake_results.get(tid, FakeResult()))

    pause_response = client.post(f"/api/pause/{task_id}")
    assert pause_response.status_code == 200
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["status"] == "paused"
    assert pause_response.json()["status"] == "paused"

    resume_response = client.post(f"/api/resume/{task_id}")
    assert resume_response.status_code == 200
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["status"] == "processing"
    assert resume_response.json()["status"] == "processing"
