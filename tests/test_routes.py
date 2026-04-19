# tests/test_routes.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.project_store as ps
    monkeypatch.setattr(ps, "PROJECTS_DIR", tmp_path / "projects")
    import web.app as app_module
    monkeypatch.setattr(app_module, "AVAILABLE_VOICES", ["de-Spk0_man", "de-Spk1_woman"])
    from web.app import app
    return TestClient(app)


def test_root_redirects_to_new_when_no_projects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "new" in r.headers["location"]


def test_new_project_form(client):
    r = client.get("/projects/new")
    assert r.status_code == 200
    assert "New Project" in r.text

def test_create_project_redirects(client):
    r = client.post("/projects", data={"name": "Test Buch", "text": "Hello World"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "test_buch" in r.headers["location"]

def test_project_view(client):
    client.post("/projects", data={"name": "My Book", "text": "Some text"})
    r = client.get("/projects/my_book")
    assert r.status_code == 200
    assert "My Book" in r.text

def test_project_not_found(client):
    r = client.get("/projects/nonexistent")
    assert r.status_code == 404

def test_preprocess_preview(client):
    client.post("/projects", data={"name": "Abbr Test", "text": "Dies ist z. B. ein Test."})
    r = client.post("/preprocess/preview", data={
        "slug": "abbr_test",
        "step_expand_abbreviations": "on",
    })
    assert r.status_code == 200
    assert "Beispiel" in r.text

def test_preprocess_full(client):
    client.post("/projects", data={"name": "Full Test", "text": "Dies ist z. B. ein Test."})
    r = client.post("/preprocess/full", data={
        "slug": "full_test",
        "step_expand_abbreviations": "on",
    })
    assert r.status_code == 200
    assert "Beispiel" in r.text


def test_create_run(client, monkeypatch):
    import web.synthesizer as synth
    import web.project_store as ps

    async def fake_launch(run_dir, settings, run_id):
        ps.update_status(run_dir.parent.parent.name, run_id, state="running", pid=0)

    monkeypatch.setattr(synth, "launch", fake_launch)
    client.post("/projects", data={"name": "Run Test", "text": "Some German text."})

    r = client.post("/projects/run_test/runs", data={
        "speaker": "de-Spk0_man",
        "max_tokens": "320",
        "cfg_scale": "1.5",
        "seed": "",
        "step_expand_abbreviations": "0",
        "step_expand_section_numbers": "0",
    }, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_serve_chunk_file(client):
    import web.project_store as ps
    client.post("/projects", data={"name": "File Test", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("file_test", settings, "text")
    run_dir = ps.PROJECTS_DIR / "file_test" / "runs" / run_id
    (run_dir / "output_00001.wav").write_bytes(b"RIFF" + b"\x00" * 40)

    r = client.get(f"/projects/file_test/runs/{run_id}/files/output_00001.wav")
    assert r.status_code == 200


def test_cancel_run(client, monkeypatch):
    import web.synthesizer as synth
    import web.project_store as ps
    monkeypatch.setattr(synth, "cancel", lambda run_id: True)

    client.post("/projects", data={"name": "Cancel Test", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("cancel_test", settings, "text")
    ps.update_status("cancel_test", run_id, state="running", pid=0)

    r = client.post(f"/projects/cancel_test/runs/{run_id}/cancel", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_sse_forwards_plan_event(client, monkeypatch):
    import web.project_store as ps
    import web.synthesizer as synth

    client.post("/projects", data={"name": "SSE Plan", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("sse_plan", settings, "text")
    ps.update_status("sse_plan", run_id, state="running", pid=0)

    async def fake_stream(run_dir, poll_interval=1.0):
        yield {"type": "plan", "chunk_count": 5}
        yield {"type": "done", "state": "done", "chunk_count": 5}

    monkeypatch.setattr(synth, "stream_chunks", fake_stream)

    r = client.get(f"/projects/sse_plan/runs/{run_id}/stream")
    assert r.status_code == 200
    assert "event: plan" in r.text
    assert "data: 5" in r.text


def test_sse_forwards_progress_event(client, monkeypatch):
    import web.project_store as ps
    import web.synthesizer as synth

    client.post("/projects", data={"name": "SSE Prog", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("sse_prog", settings, "text")
    ps.update_status("sse_prog", run_id, state="running", pid=0)

    async def fake_stream(run_dir, poll_interval=1.0):
        yield {"type": "progress", "current_chunk": 2}
        yield {"type": "done", "state": "done", "chunk_count": 5}

    monkeypatch.setattr(synth, "stream_chunks", fake_stream)

    r = client.get(f"/projects/sse_prog/runs/{run_id}/stream")
    assert r.status_code == 200
    assert "event: progress" in r.text
    assert "data: 2" in r.text


def test_sse_done_payload_is_json(client, monkeypatch):
    import web.project_store as ps
    import web.synthesizer as synth
    import json

    client.post("/projects", data={"name": "SSE Done", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("sse_done", settings, "text")
    run_dir = ps.PROJECTS_DIR / "sse_done" / "runs" / run_id
    (run_dir / "output_00001.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    ps.update_status("sse_done", run_id, state="running", pid=0)

    async def fake_stream(run_dir, poll_interval=1.0):
        yield {"type": "done", "state": "done", "chunk_count": 1}

    monkeypatch.setattr(synth, "stream_chunks", fake_stream)

    r = client.get(f"/projects/sse_done/runs/{run_id}/stream")
    assert r.status_code == 200
    assert "event: done" in r.text
    for line in r.text.splitlines():
        if line.startswith("data:") and "state" in line:
            payload = json.loads(line[len("data:"):].strip())
            assert payload["state"] == "done"
            assert payload["final_url"] is not None
            assert "/download" in payload["final_url"]
            break


def test_prev_runs_have_queue_buttons(client):
    import web.project_store as ps
    client.post("/projects", data={"name": "Queue Prev", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("queue_prev", settings, "text")
    ps.update_status("queue_prev", run_id, state="done", chunk_count=1)

    r = client.get("/projects/queue_prev")
    assert r.status_code == 200
    assert "btn-queue" in r.text
    assert "<audio" not in r.text


def test_player_bar_present(client):
    r = client.get("/projects/new")
    assert r.status_code == 200
    assert 'id="player-bar"' in r.text


def test_run_view_has_queue_buttons(client):
    import web.project_store as ps
    client.post("/projects", data={"name": "Run View Q", "text": "text"})
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = ps.create_run("run_view_q", settings, "text")
    run_dir = ps.PROJECTS_DIR / "run_view_q" / "runs" / run_id
    (run_dir / "output_00001.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    (run_dir / "output_00001.txt").write_text("Test snippet")
    (run_dir / "output.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    ps.update_status("run_view_q", run_id, state="done", chunk_count=1)

    r = client.get(f"/projects/run_view_q/runs/{run_id}")
    assert r.status_code == 200
    assert "btn-queue" in r.text
    assert "<audio" not in r.text
