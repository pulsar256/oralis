from __future__ import annotations
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path(__file__).parent.parent / "projects"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


@dataclass
class Project:
    slug: str
    name: str
    created_at: str
    source_text: str


@dataclass
class Run:
    run_id: str
    settings: dict
    status: dict


def _project_dir(slug: str) -> Path:
    return PROJECTS_DIR / slug


def _run_dir(slug: str, run_id: str) -> Path:
    return _project_dir(slug) / "runs" / run_id


def _update_status_file(run_dir: Path, **kwargs) -> None:
    path = run_dir / "status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    status.update(kwargs)
    path.write_text(json.dumps(status), encoding="utf-8")


def create_project(name: str, text: str) -> Project:
    slug = slugify(name)
    d = _project_dir(slug)
    d.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    (d / "project.json").write_text(json.dumps({"name": name, "created_at": created_at}), encoding="utf-8")
    (d / "source.txt").write_text(text, encoding="utf-8")
    return Project(slug=slug, name=name, created_at=created_at, source_text=text)


def get_project(slug: str) -> Project | None:
    d = _project_dir(slug)
    if not d.exists():
        return None
    meta = json.loads((d / "project.json").read_text(encoding="utf-8"))
    text = (d / "source.txt").read_text(encoding="utf-8")
    return Project(slug=slug, name=meta["name"], created_at=meta["created_at"], source_text=text)


def list_projects() -> list[Project]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if d.is_dir() and (d / "project.json").exists():
            p = get_project(d.name)
            if p:
                result.append(p)
    return result


def create_run(slug: str, settings: dict, preprocessed_text: str) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    d = _run_dir(slug, run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.json").write_text(json.dumps(settings, indent=2))
    (d / "preprocessed.txt").write_text(preprocessed_text, encoding="utf-8")
    status = {"state": "pending", "chunk_count": None, "current_chunk": 0,
              "elapsed_times": [], "pid": None}
    (d / "status.json").write_text(json.dumps(status))
    return run_id


def get_run(slug: str, run_id: str) -> Run | None:
    d = _run_dir(slug, run_id)
    if not d.exists():
        return None
    settings = json.loads((d / "settings.json").read_text())
    status = json.loads((d / "status.json").read_text())
    return Run(run_id=run_id, settings=settings, status=status)


def list_runs(slug: str) -> list[Run]:
    runs_dir = _project_dir(slug) / "runs"
    if not runs_dir.exists():
        return []
    result = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if d.is_dir():
            r = get_run(slug, d.name)
            if r:
                result.append(r)
    return result


def delete_project(slug: str) -> None:
    shutil.rmtree(_project_dir(slug), ignore_errors=True)


def update_source_text(slug: str, text: str) -> None:
    (_project_dir(slug) / "source.txt").write_text(text, encoding="utf-8")


def rename_project(slug: str, new_name: str) -> None:
    d = _project_dir(slug)
    meta = json.loads((d / "project.json").read_text(encoding="utf-8"))
    meta["name"] = new_name
    (d / "project.json").write_text(json.dumps(meta), encoding="utf-8")


def rename_run(slug: str, run_id: str, name: str) -> None:
    path = _run_dir(slug, run_id) / "settings.json"
    settings = json.loads(path.read_text())
    if name:
        settings["name"] = name
    else:
        settings.pop("name", None)
    path.write_text(json.dumps(settings, indent=2))


def delete_run(slug: str, run_id: str) -> None:
    shutil.rmtree(_run_dir(slug, run_id), ignore_errors=True)


def update_status(slug: str, run_id: str, **kwargs) -> None:
    _update_status_file(_run_dir(slug, run_id), **kwargs)


def get_chunks(slug: str, run_id: str) -> list[dict]:
    d = _run_dir(slug, run_id)
    chunks = []
    for wav in sorted(d.glob("output_?????.wav")):
        index = int(wav.stem.rsplit("_", 1)[-1])
        txt = wav.with_suffix(".txt")
        snippet = txt.read_text(encoding="utf-8")[:120] if txt.exists() else ""
        chunks.append({"index": index, "wav_name": wav.name, "snippet": snippet,
                       "size": wav.stat().st_size})
    return chunks
