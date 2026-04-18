import asyncio
import json
import pytest
from pathlib import Path


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    (d / "status.json").write_text(json.dumps({
        "state": "running", "chunk_count": None,
        "current_chunk": 0, "elapsed_times": [], "pid": None,
    }))
    return d


async def test_stream_chunks_done_immediately(run_dir):
    from web.synthesizer import stream_chunks
    status = json.loads((run_dir / "status.json").read_text())
    status["state"] = "done"
    (run_dir / "status.json").write_text(json.dumps(status))

    events = [e async for e in stream_chunks(run_dir, poll_interval=0.01)]
    assert events == [{"type": "done", "state": "done", "chunk_count": 0}]


async def test_stream_chunks_detects_new_wav(run_dir):
    from web.synthesizer import stream_chunks

    async def writer():
        await asyncio.sleep(0.05)
        (run_dir / "output_00001.wav").write_bytes(b"RIFF")
        (run_dir / "output_00001.txt").write_text("First chunk text")
        await asyncio.sleep(0.05)
        s = json.loads((run_dir / "status.json").read_text())
        s["state"] = "done"
        (run_dir / "status.json").write_text(json.dumps(s))

    events = []
    task = asyncio.create_task(writer())
    async for e in stream_chunks(run_dir, poll_interval=0.02):
        events.append(e)
    await task

    assert events[0]["type"] == "chunk"
    assert events[0]["index"] == 1
    assert "First chunk" in events[0]["snippet"]
    assert events[-1]["type"] == "done"


def test_cancel_unknown_run_returns_false():
    from web.synthesizer import cancel
    assert cancel("no-such-run") is False


async def test_stream_chunks_emits_plan_event(run_dir):
    from web.synthesizer import stream_chunks
    import json

    (run_dir / "progress.json").write_text(
        json.dumps({"chunk_count": 3, "current_chunk": 0})
    )
    s = json.loads((run_dir / "status.json").read_text())
    s["state"] = "done"
    (run_dir / "status.json").write_text(json.dumps(s))

    events = [e async for e in stream_chunks(run_dir, poll_interval=0.01)]
    plan_events = [e for e in events if e["type"] == "plan"]
    assert len(plan_events) == 1
    assert plan_events[0]["chunk_count"] == 3


async def test_stream_chunks_emits_progress_event(run_dir):
    from web.synthesizer import stream_chunks
    import json

    (run_dir / "progress.json").write_text(
        json.dumps({"chunk_count": 3, "current_chunk": 2})
    )
    s = json.loads((run_dir / "status.json").read_text())
    s["state"] = "done"
    (run_dir / "status.json").write_text(json.dumps(s))

    events = [e async for e in stream_chunks(run_dir, poll_interval=0.01)]
    progress_events = [e for e in events if e["type"] == "progress"]
    assert len(progress_events) == 1
    assert progress_events[0]["current_chunk"] == 2


async def test_stream_chunks_no_progress_file_still_works(run_dir):
    from web.synthesizer import stream_chunks
    import json

    s = json.loads((run_dir / "status.json").read_text())
    s["state"] = "done"
    (run_dir / "status.json").write_text(json.dumps(s))

    events = [e async for e in stream_chunks(run_dir, poll_interval=0.01)]
    assert events == [{"type": "done", "state": "done", "chunk_count": 0}]
