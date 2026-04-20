from __future__ import annotations
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import AsyncIterator

from web.project_store import _update_status_file

log = logging.getLogger(__name__)

_active: dict[str, asyncio.subprocess.Process] = {}
_ANSI = re.compile(rb'\x1b\[[0-9;]*[A-Za-z]')


async def _read_stdout(stream, run_id: str) -> None:
    async for raw in stream:
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line:
            log.info("[%s] %s", run_id, line)


async def _read_stderr(stream, log_path: Path, status_path: Path, run_id: str) -> None:
    """Read stderr pipe: log raw bytes to disk, extract current tqdm display line to status_path."""
    log_fh = log_path.open("wb")
    current_line = ""
    last_write = 0.0
    try:
        while True:
            chunk = await stream.read(512)
            if not chunk:
                break
            log_fh.write(chunk)
            log_fh.flush()
            text = _ANSI.sub(b"", chunk).decode("utf-8", errors="replace")
            for ch in text:
                if ch == "\r":
                    if current_line.strip():
                        log.debug("[%s] %s", run_id, current_line.strip())
                    current_line = ""
                elif ch == "\n":
                    if current_line.strip():
                        log.debug("[%s] %s", run_id, current_line.strip())
                    current_line = ""
                else:
                    current_line += ch
            now = time.monotonic()
            line = current_line.strip()
            if line and now - last_write >= 0.5:
                try:
                    status_path.write_text(line, encoding="utf-8")
                    last_write = now
                except OSError:
                    pass
    finally:
        log_fh.close()


def _oralis_bin() -> str:
    # Use the oralis script installed in the active venv — same Python env, no uv re-sync.
    return str(Path(sys.executable).parent / "oralis")


async def launch(run_dir: Path, settings: dict, run_id: str) -> None:
    repo_root = Path(__file__).parent.parent
    cmd = [
        _oralis_bin(),
        "--input",      str(run_dir / "preprocessed.txt"),
        "--output",     str(run_dir / "output.wav"),
        "--speaker",    settings["speaker"],
        "--max-tokens", str(settings["max_tokens"]),
        "--cfg-scale",  str(settings["cfg_scale"]),
    ]
    if settings.get("seed") is not None:
        cmd += ["--seed", str(settings["seed"])]
    cmd += ["--progress-file", str(run_dir / "progress.json")]

    log.info("[%s] starting: %s", run_id, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=repo_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    log.info("[%s] pid=%d", run_id, proc.pid)
    _active[run_id] = proc
    _update_status_file(run_dir, state="running", pid=proc.pid)
    asyncio.create_task(_read_stdout(proc.stdout, run_id))
    asyncio.create_task(_read_stderr(proc.stderr, run_dir / "stderr.log", run_dir / "status.txt", run_id))
    asyncio.create_task(_monitor(proc, run_dir, run_id))


async def _monitor(proc: asyncio.subprocess.Process, run_dir: Path, run_id: str) -> None:
    await proc.wait()
    _active.pop(run_id, None)
    # Don't overwrite a "stopped" state set by the user via cancel()
    try:
        current = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        if current.get("state") == "stopped":
            return
    except (json.JSONDecodeError, OSError):
        pass
    # Negative returncode means killed by a signal (OOM, external kill -9, etc.) — resumable
    if proc.returncode == 0:
        state = "done"
    elif proc.returncode < 0:
        state = "stopped"
    else:
        state = "failed"
    log.info("[%s] exited rc=%d state=%s", run_id, proc.returncode, state)
    chunk_count = len(list(run_dir.glob("output_?????.wav")))
    _update_status_file(run_dir, state=state, chunk_count=chunk_count)


def cancel(run_id: str) -> bool:
    proc = _active.get(run_id)
    if proc:
        proc.terminate()
        return True
    return False


async def stream_chunks(run_dir: Path, poll_interval: float = 1.0) -> AsyncIterator[dict]:
    seen: set[str] = set()
    last_chunk_count: int | None = None
    last_current_chunk: int = 0
    last_status: str = ""
    progress_file = run_dir / "progress.json"
    status_file = run_dir / "status.txt"

    while True:
        # Poll progress.json for plan/progress events
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
            chunk_count = progress.get("chunk_count")
            current_chunk = progress.get("current_chunk", 0)

            if chunk_count is not None and last_chunk_count is None:
                last_chunk_count = chunk_count
                yield {"type": "plan", "chunk_count": chunk_count}

            if current_chunk != last_current_chunk:
                last_current_chunk = current_chunk
                if current_chunk > 0:
                    yield {"type": "progress", "current_chunk": current_chunk}
        except (json.JSONDecodeError, OSError):
            pass

        # Poll status.txt for live stderr/tqdm updates
        try:
            line = status_file.read_text(encoding="utf-8").strip()
            if line and line != last_status:
                last_status = line
                yield {"type": "status", "text": line}
        except OSError:
            pass

        # Poll for newly completed .wav files
        for wav in sorted(run_dir.glob("output_?????.wav")):
            if wav.name not in seen:
                txt = wav.with_suffix(".txt")
                if not txt.exists():
                    continue  # txt not written yet; pick up next poll
                seen.add(wav.name)
                snippet = txt.read_text(encoding="utf-8")[:120]
                index = int(wav.stem.rsplit("_", 1)[-1])
                yield {"type": "chunk", "index": index,
                       "snippet": snippet, "wav_name": wav.name}

        # Check if subprocess finished
        try:
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            await asyncio.sleep(poll_interval)
            continue

        if status["state"] in ("done", "failed", "stopped"):
            yield {"type": "done", "state": status["state"],
                   "chunk_count": last_chunk_count or len(seen)}
            return

        await asyncio.sleep(poll_interval)
