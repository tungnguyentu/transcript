from fastapi.testclient import TestClient

from transcript_tool import web


def test_index_renders_form():
    client = TestClient(web.app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Transcript Tool Web UI" in response.text
    assert "id=\"upload-form\"" in response.text


def test_transcribe_endpoint(monkeypatch, tmp_path):
    client = TestClient(web.app)

    output_dir = tmp_path / "subs"
    monkeypatch.setattr(web, "OUTPUT_DIR", output_dir)

    def fake_transcribe_media(input_path, **kwargs):
        transcript_path = input_path.with_suffix(".txt")
        subtitle_path = input_path.with_suffix(".srt")
        transcript_path.write_text("hello world", encoding="utf-8")
        subtitle_path.write_text("subtitle content", encoding="utf-8")
        return transcript_path, subtitle_path

    class InlineExecutor:
        def submit(self, func, *args, **kwargs):
            func(*args, **kwargs)

            class _CompletedFuture:
                def result(self):
                    return None

            return _CompletedFuture()

    monkeypatch.setattr(web, "transcribe_media", fake_transcribe_media)
    monkeypatch.setattr(web, "EXECUTOR", InlineExecutor())
    web.TASKS.clear()
    web.TASK_CONTROLS.clear()

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

    web.TASKS.clear()
    web.TASK_CONTROLS.clear()


def test_pause_and_resume_controls():
    client = TestClient(web.app)
    web.TASKS.clear()
    web.TASK_CONTROLS.clear()

    task_id = "dummy"
    state = web.TaskState(status="processing", progress=30, message="Processing")
    control = web.TaskControl()
    web.TASKS[task_id] = state
    web.TASK_CONTROLS[task_id] = control

    pause_response = client.post(f"/api/pause/{task_id}")
    assert pause_response.status_code == 200
    assert not control.pause_event.is_set()
    assert pause_response.json()["status"] == "paused"
    assert web.TASKS[task_id].paused is True

    resume_response = client.post(f"/api/resume/{task_id}")
    assert resume_response.status_code == 200
    assert control.pause_event.is_set()
    assert resume_response.json()["status"] == "processing"
    assert web.TASKS[task_id].paused is False

    web.TASKS.clear()
    web.TASK_CONTROLS.clear()
