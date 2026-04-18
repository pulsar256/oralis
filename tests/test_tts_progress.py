# tests/test_tts_progress.py
import json
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import oralis as tts


def test_write_progress_noop_when_path_is_none(tmp_path):
    tts._write_progress(None, {"chunk_count": 5})
    assert not any(tmp_path.iterdir())


def test_write_progress_creates_file(tmp_path):
    p = str(tmp_path / "progress.json")
    tts._write_progress(p, {"chunk_count": 5, "current_chunk": 0})
    data = json.loads(Path(p).read_text())
    assert data == {"chunk_count": 5, "current_chunk": 0}


def test_write_progress_merges_into_existing(tmp_path):
    p = str(tmp_path / "progress.json")
    tts._write_progress(p, {"chunk_count": 5, "current_chunk": 0})
    tts._write_progress(p, {"current_chunk": 2})
    data = json.loads(Path(p).read_text())
    assert data == {"chunk_count": 5, "current_chunk": 2}


def test_write_progress_survives_corrupt_file(tmp_path):
    p = tmp_path / "progress.json"
    p.write_text("not json")
    tts._write_progress(str(p), {"chunk_count": 3})
    data = json.loads(p.read_text())
    assert data["chunk_count"] == 3


def test_parse_args_accepts_progress_file(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["oralis.py", "--progress-file", "/tmp/p.json", "hello"])
    args = tts.parse_args()
    assert args.progress_file == "/tmp/p.json"


def test_parse_args_progress_file_defaults_to_none(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["oralis.py", "hello"])
    args = tts.parse_args()
    assert args.progress_file is None


def test_write_progress_overwrites_current_chunk(tmp_path):
    p = str(tmp_path / "progress.json")
    tts._write_progress(p, {"chunk_count": 5, "current_chunk": 0})
    tts._write_progress(p, {"current_chunk": 1})
    tts._write_progress(p, {"current_chunk": 2})
    data = json.loads(Path(p).read_text())
    assert data["chunk_count"] == 5
    assert data["current_chunk"] == 2
