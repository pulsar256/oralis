import pytest
from web.project_store import (
    slugify, create_project, get_project, list_projects,
    create_run, get_run, list_runs, update_status, get_chunks,
)

@pytest.fixture(autouse=True)
def tmp_projects(tmp_path, monkeypatch):
    import web.project_store as ps
    monkeypatch.setattr(ps, "PROJECTS_DIR", tmp_path / "projects")

def test_slugify():
    assert slugify("Agile Buch") == "agile_buch"
    assert slugify("  Hello World!  ") == "hello_world"

def test_create_and_get_project():
    p = create_project("Agile Buch", "Some text")
    assert p.slug == "agile_buch"
    assert p.name == "Agile Buch"
    assert p.source_text == "Some text"
    p2 = get_project("agile_buch")
    assert p2.name == "Agile Buch"

def test_list_projects_empty():
    assert list_projects() == []

def test_list_projects():
    create_project("A", "text a")
    create_project("B", "text b")
    slugs = [p.slug for p in list_projects()]
    assert "a" in slugs and "b" in slugs

def test_create_run():
    create_project("Proj", "text")
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = create_run("proj", settings, "preprocessed")
    run = get_run("proj", run_id)
    assert run.settings["speaker"] == "de-Spk0_man"
    assert run.status["state"] == "pending"

def test_update_status():
    create_project("Proj2", "text")
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = create_run("proj2", settings, "text")
    update_status("proj2", run_id, state="running", pid=1234)
    run = get_run("proj2", run_id)
    assert run.status["state"] == "running"
    assert run.status["pid"] == 1234

def test_get_chunks_empty():
    create_project("Proj3", "text")
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = create_run("proj3", settings, "text")
    assert get_chunks("proj3", run_id) == []

def test_get_chunks_with_files():
    create_project("Proj4", "text")
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id = create_run("proj4", settings, "text")
    import web.project_store as ps
    run_dir = ps.PROJECTS_DIR / "proj4" / "runs" / run_id
    (run_dir / "output_00001.wav").write_bytes(b"RIFF")
    (run_dir / "output_00001.txt").write_text("Chunk one text")
    chunks = get_chunks("proj4", run_id)
    assert len(chunks) == 1
    assert chunks[0]["index"] == 1
    assert chunks[0]["snippet"] == "Chunk one text"


def test_list_runs():
    create_project("Proj5", "text")
    settings = {"speaker": "de-Spk0_man", "max_tokens": 320, "cfg_scale": 1.5,
                "seed": None, "preprocessor": {"steps": []}}
    run_id_1 = create_run("proj5", settings, "text")
    import time; time.sleep(1.1)  # ensure different timestamps
    run_id_2 = create_run("proj5", settings, "text")
    runs = list_runs("proj5")
    assert len(runs) == 2
    assert runs[0].run_id == run_id_2  # most recent first
    assert runs[1].run_id == run_id_1
