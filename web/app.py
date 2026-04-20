# web/app.py
from __future__ import annotations
import asyncio
import json
import logging
import math
import os
import struct
import subprocess
import sys
import wave
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import web.project_store as store
from web.preprocessor import apply_steps, preview, full_diff, default_steps, KNOWN_STEPS
from web import synthesizer

BASE_DIR = Path(__file__).parent

AVAILABLE_VOICES: list[str] = []


async def _load_voices() -> None:
    global AVAILABLE_VOICES
    try:
        oralis = str(Path(sys.executable).parent / "oralis")
        result = subprocess.run(
            [oralis, "--list-voices"],
            capture_output=True, text=True, timeout=30,
            cwd=BASE_DIR.parent,
        )
        voices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        AVAILABLE_VOICES = voices if voices else ["en-breeze_woman", "de-Spk0_man"]
    except Exception:
        AVAILABLE_VOICES = ["en-breeze_woman", "de-Spk0_man"]


def _configure_logging() -> None:
    level_name = os.environ.get("LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.INFO)
    log = logging.getLogger("web")
    log.setLevel(level)
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s - %(message)s"))
        log.addHandler(handler)
        log.propagate = False


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _configure_logging()
    await _load_voices()
    yield


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _ctx(active_slug: str | None = None, **extra) -> dict:
    return {"projects": store.list_projects(), "active_slug": active_slug, **extra}


def _step_list_from_form(form) -> list[dict]:
    return [
        {"id": s["id"], "label": s["label"],
         "enabled": form.get(f"step_{s['id']}") in ("on", "1")}
        for s in KNOWN_STEPS
    ]


def _merge_steps(saved: list[dict]) -> list[dict]:
    saved_by_id = {s["id"]: s for s in saved}
    return [
        {"id": s["id"], "label": s["label"],
         "enabled": saved_by_id[s["id"]]["enabled"] if s["id"] in saved_by_id
                    else s["id"] in ("normalize_unicode", "strip_formatting")}
        for s in KNOWN_STEPS
    ]


def _last_settings(runs) -> dict:
    defaults = {"speaker": AVAILABLE_VOICES[0] if AVAILABLE_VOICES else "en-breeze_woman",
                "max_tokens": 512, "cfg_scale": 1.5, "seed": None}
    if runs:
        s = runs[0].settings
        return {k: s.get(k, defaults[k]) for k in defaults}
    return defaults


@app.get("/")
async def root():
    projects = store.list_projects()
    if projects:
        return RedirectResponse(f"/projects/{projects[0].slug}")
    return RedirectResponse("/projects/new")


@app.get("/projects/new")
async def new_project_form(request: Request):
    return templates.TemplateResponse(request, "project_new.html", _ctx())


@app.post("/projects")
async def create_project(
    request: Request,
    name: str = Form(...),
    text: str = Form(""),
    file: UploadFile | None = File(None),
):
    if file and file.filename:
        text = (await file.read()).decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(400, "Provide text or upload a file")
    p = store.create_project(name, text)
    return RedirectResponse(f"/projects/{p.slug}", status_code=303)


@app.get("/projects/{slug}")
async def project_view(request: Request, slug: str):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    all_runs = store.list_runs(slug)
    
    # Check for stalled running runs
    for r in all_runs:
        if r.status["state"] == "running":
            pid = r.status.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)
                except OSError:
                    store.update_status(slug, r.run_id, state="stopped")
                    r.status["state"] = "stopped"

    # Prepare runs with their chunks and final audio status
    runs_data = []
    for r in all_runs:
        run_dir = store.PROJECTS_DIR / slug / "runs" / r.run_id
        chunks = store.get_chunks(slug, r.run_id)
        runs_data.append({
            "run": r,
            "chunks": chunks,
            "has_final": (run_dir / "output.wav").exists() or bool(chunks)
        })

    saved = (all_runs[0].settings.get("preprocessor", {}).get("steps") or []) if all_runs else []
    steps = _merge_steps(saved) if saved else default_steps()
    
    return templates.TemplateResponse(request, "project.html", _ctx(
        active_slug=slug,
        project=project,
        steps=steps,
        voices=AVAILABLE_VOICES,
        last=_last_settings(all_runs),
        preview_html=preview(project.source_text, steps),
        source_kb=round(len(project.source_text.encode()) / 1024, 1),
        runs=runs_data,
    ))


@app.get("/projects/{slug}/source")
async def replace_source_form(request: Request, slug: str):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "project_source.html", _ctx(active_slug=slug, project=project))


@app.post("/projects/{slug}/source")
async def replace_source(slug: str, text: str = Form(""), file: UploadFile | None = File(None)):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    if file and file.filename:
        text = (await file.read()).decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(400, "Provide text or upload a file")
    store.update_source_text(slug, text)
    return RedirectResponse(f"/projects/{slug}", status_code=303)


@app.post("/preprocess/preview", response_class=HTMLResponse)
async def preprocess_preview(request: Request, slug: str = Form(...)):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    steps = _step_list_from_form(await request.form())
    return HTMLResponse(preview(project.source_text, steps))


@app.post("/preprocess/full", response_class=HTMLResponse)
async def preprocess_full(request: Request, slug: str = Form(...)):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    steps = _step_list_from_form(await request.form())
    return HTMLResponse(full_diff(project.source_text, steps))


@app.get("/projects/{slug}/preprocessed")
async def download_preprocessed(slug: str):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    runs = store.list_runs(slug)
    saved = (runs[0].settings.get("preprocessor", {}).get("steps") or []) if runs else []
    steps = _merge_steps(saved) if saved else default_steps()
    text = apply_steps(project.source_text, steps)
    return Response(content=text.encode(), media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{slug}_preprocessed.txt"'})


@app.post("/projects/{slug}/runs")
async def create_run(request: Request, slug: str):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    form = await request.form()
    speaker = form.get("speaker", AVAILABLE_VOICES[0] if AVAILABLE_VOICES else "de-Spk0_man")
    max_tokens = int(form.get("max_tokens", 512))
    cfg_scale = float(form.get("cfg_scale", 1.5))
    seed_raw = str(form.get("seed", "")).strip()
    steps = _step_list_from_form(form)
    settings = {
        "speaker": speaker, "max_tokens": max_tokens,
        "cfg_scale": cfg_scale,
        "seed": int(seed_raw) if seed_raw else None,
        "preprocessor": {"steps": steps},
    }
    preprocessed = apply_steps(project.source_text, steps)
    run_id = store.create_run(slug, settings, preprocessed)
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    await synthesizer.launch(run_dir, settings, run_id)
    return RedirectResponse(f"/projects/{slug}", status_code=303)


@app.get("/projects/{slug}/runs/{run_id}")
async def run_view(request: Request, slug: str, run_id: str):
    project = store.get_project(slug)
    run = store.get_run(slug, run_id)
    if not project or not run:
        raise HTTPException(404)
    chunks = store.get_chunks(slug, run_id)
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    has_final = (run_dir / "output.wav").exists() or bool(chunks)
    return templates.TemplateResponse(request, "run_view.html", _ctx(
        active_slug=slug,
        project=project,
        run=run,
        chunks=chunks,
        has_final=has_final,
    ))


@app.get("/projects/{slug}/runs/{run_id}/stream")
async def run_stream(slug: str, run_id: str):
    project = store.get_project(slug)
    run = store.get_run(slug, run_id)
    if not project or not run:
        raise HTTPException(404)
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    if run.status.get("state") in ("done", "failed", "stopped"):
        seen_names: set[str] = set()
    else:
        seen_names = {c["wav_name"] for c in store.get_chunks(slug, run_id)}

    async def generate():
        nonlocal seen_names
        async for event in synthesizer.stream_chunks(run_dir):
            if event["type"] == "plan":
                yield f"event: plan\ndata: {event['chunk_count']}\n\n"
            elif event["type"] == "progress":
                yield f"event: progress\ndata: {event['current_chunk']}\n\n"
            elif event["type"] == "status":
                yield f"event: status\ndata: {event['text']}\n\n"
            elif event["type"] == "chunk" and event["wav_name"] not in seen_names:
                seen_names.add(event["wav_name"])
                html = " ".join(templates.get_template("run_chunk.html").render(
                    project=project, run=run, chunk=event).split())
                yield f"event: chunk\ndata: {html}\n\n"
            elif event["type"] == "done":
                has_audio = any(run_dir.glob("output_?????.wav"))
                final_url = f"/projects/{slug}/runs/{run_id}/download" if has_audio else None
                payload = json.dumps({"state": event["state"], "final_url": final_url})
                yield f"event: done\ndata: {payload}\n\n"
                return

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/projects/{slug}/runs/{run_id}/files/{filename}")
async def serve_file(slug: str, run_id: str, filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(403)
    if not filename.endswith((".wav", ".txt")):
        raise HTTPException(403)
    run_dir = (store.PROJECTS_DIR / slug / "runs" / run_id).resolve()
    path = (run_dir / filename).resolve()
    if not path.is_relative_to(run_dir):
        raise HTTPException(403)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


def _waveform_json(wav_path: Path) -> bytes:
    sidecar = wav_path.with_suffix(".waveform.json")
    if sidecar.exists():
        return sidecar.read_bytes()
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        framerate = wf.getframerate()
        duration = n_frames / framerate
        n_buckets = 600
        window = max(1, n_frames // n_buckets)
        buckets = []
        for i in range(n_buckets):
            start = i * window
            if start >= n_frames:
                buckets.append(0.0)
                continue
            wf.setpos(start)
            count = min(window, n_frames - start)
            raw = wf.readframes(count)
            if sampwidth == 2:
                unpacked = struct.unpack(f"<{count * n_channels}h", raw)
                ch0 = [unpacked[j * n_channels] / 32768.0 for j in range(count)]
            elif sampwidth == 1:
                ch0 = [(raw[j * n_channels] - 128) / 128.0 for j in range(count)]
            else:
                ch0 = [0.0] * count
            rms = math.sqrt(sum(x * x for x in ch0) / len(ch0)) if ch0 else 0.0
            buckets.append(rms)
    peak = max(buckets) if buckets else 1.0
    if peak > 0:
        buckets = [v / peak for v in buckets]
    result = json.dumps({"samples": buckets, "duration": duration}).encode()
    sidecar.write_bytes(result)
    return result


@app.get("/projects/{slug}/runs/{run_id}/files/{filename}/waveform")
async def serve_waveform(slug: str, run_id: str, filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(403)
    if not filename.endswith(".wav"):
        raise HTTPException(403)
    run_dir = (store.PROJECTS_DIR / slug / "runs" / run_id).resolve()
    wav_path = (run_dir / filename).resolve()
    if not wav_path.is_relative_to(run_dir):
        raise HTTPException(403)
    if not wav_path.is_file():
        raise HTTPException(404)
    data = await asyncio.get_running_loop().run_in_executor(None, _waveform_json, wav_path)
    return Response(data, media_type="application/json")


@app.get("/projects/{slug}/runs/{run_id}/chunks/{wav_name}/download-mp3")
async def download_chunk_mp3(slug: str, run_id: str, wav_name: str):
    if "/" in wav_name or "\\" in wav_name or ".." in wav_name or not wav_name.endswith(".wav"):
        raise HTTPException(403)
    run_dir = (store.PROJECTS_DIR / slug / "runs" / run_id).resolve()
    wav_path = (run_dir / wav_name).resolve()
    if not wav_path.is_relative_to(run_dir) or not wav_path.is_file():
        raise HTTPException(404)
    mp3_path = run_dir / wav_name.replace(".wav", ".mp3")
    if not mp3_path.exists():
        def _transcode():
            tmp = mp3_path.with_suffix(".mp3.tmp")
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
                 "-codec:a", "libmp3lame", "-q:a", "2", "-f", "mp3", str(tmp)],
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode())
            tmp.rename(mp3_path)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _transcode)
        except Exception as exc:
            raise HTTPException(500, f"Transcoding failed: {exc}") from exc
    stem = wav_name.replace(".wav", "")
    return FileResponse(mp3_path, filename=f"{slug}_{run_id}_{stem}.mp3", media_type="audio/mpeg")


@app.get("/projects/{slug}/runs/{run_id}/chunks/{wav_name}/download-mp4")
async def download_chunk_mp4(slug: str, run_id: str, wav_name: str):
    if "/" in wav_name or "\\" in wav_name or ".." in wav_name or not wav_name.endswith(".wav"):
        raise HTTPException(403)
    run_dir = (store.PROJECTS_DIR / slug / "runs" / run_id).resolve()
    wav_path = (run_dir / wav_name).resolve()
    if not wav_path.is_relative_to(run_dir) or not wav_path.is_file():
        raise HTTPException(404)
    mp4_path = run_dir / wav_name.replace(".wav", ".mp4")
    if not mp4_path.exists():
        def _transcode():
            tmp = mp4_path.with_suffix(".mp4.tmp")
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=c=#111111:s=320x40:r=1",
                 "-i", str(wav_path),
                 "-shortest", "-c:v", "libx264", "-tune", "stillimage",
                 "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(tmp)],
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode())
            tmp.rename(mp4_path)
        try:
            await asyncio.get_running_loop().run_in_executor(None, _transcode)
        except Exception as exc:
            raise HTTPException(500, f"Transcoding failed: {exc}") from exc
    stem = wav_name.replace(".wav", "")
    return FileResponse(mp4_path, filename=f"{slug}_{run_id}_{stem}.mp4", media_type="video/mp4")


@app.get("/projects/{slug}/runs/{run_id}/download/waveform")
async def download_waveform(slug: str, run_id: str):
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    wav_path = run_dir / "output.wav"
    if not wav_path.exists():
        wavs = sorted(run_dir.glob("output_?????.wav"))
        if not wavs:
            raise HTTPException(404)
        wav_path = wavs[0]
    data = await asyncio.get_running_loop().run_in_executor(None, _waveform_json, wav_path)
    return Response(data, media_type="application/json")


@app.get("/projects/{slug}/runs/{run_id}/download")
async def download_final(slug: str, run_id: str):
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    final = run_dir / "output.wav"
    if not final.exists():
        wavs = sorted(run_dir.glob("output_?????.wav"))
        if not wavs:
            raise HTTPException(404)
        final = wavs[0]
    return FileResponse(final, filename=f"{slug}_{run_id}.wav")


@app.get("/projects/{slug}/runs/{run_id}/download-mp3")
async def download_mp3(slug: str, run_id: str):
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    mp3_path = run_dir / "output.mp3"

    if not mp3_path.exists():
        wav = run_dir / "output.wav"
        if not wav.exists():
            wavs = sorted(run_dir.glob("output_?????.wav"))
            if not wavs:
                raise HTTPException(404)
            wav = wavs[0]

        def _transcode():
            tmp = mp3_path.with_suffix(".mp3.tmp")
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                 "-codec:a", "libmp3lame", "-q:a", "2", "-f", "mp3", str(tmp)],
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode())
            tmp.rename(mp3_path)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _transcode)
        except Exception as exc:
            raise HTTPException(500, f"Transcoding failed: {exc}") from exc

    return FileResponse(mp3_path, filename=f"{slug}_{run_id}.mp3", media_type="audio/mpeg")


@app.get("/projects/{slug}/runs/{run_id}/download-mp4")
async def download_mp4(slug: str, run_id: str):
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    mp4_path = run_dir / "output.mp4"

    if not mp4_path.exists():
        wav = run_dir / "output.wav"
        if not wav.exists():
            wavs = sorted(run_dir.glob("output_?????.wav"))
            if not wavs:
                raise HTTPException(404)
            wav = wavs[0]

        def _transcode():
            tmp = mp4_path.with_suffix(".mp4.tmp")
            result = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=c=#111111:s=320x40:r=1",
                 "-i", str(wav),
                 "-shortest", "-c:v", "libx264", "-tune", "stillimage",
                 "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(tmp)],
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode())
            tmp.rename(mp4_path)

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _transcode)
        except Exception as exc:
            raise HTTPException(500, f"Transcoding failed: {exc}") from exc

    return FileResponse(mp4_path, filename=f"{slug}_{run_id}.mp4", media_type="video/mp4")


@app.post("/projects/{slug}/delete")
async def delete_project_route(slug: str):
    if not store.get_project(slug):
        raise HTTPException(404)
    store.delete_project(slug)
    projects = store.list_projects()
    target = f"/projects/{projects[0].slug}" if projects else "/projects/new"
    return RedirectResponse(target, status_code=303)


@app.post("/projects/{slug}/rename")
async def rename_project_route(slug: str, name: str = Form(...)):
    project = store.get_project(slug)
    if not project:
        raise HTTPException(404)
    name = name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    store.rename_project(slug, name)
    return RedirectResponse(f"/projects/{slug}", status_code=303)


@app.post("/projects/{slug}/runs/{run_id}/rename")
async def rename_run_route(slug: str, run_id: str, name: str = Form(...)):
    if not store.get_run(slug, run_id):
        raise HTTPException(404)
    store.rename_run(slug, run_id, name.strip())
    return Response(status_code=204)


@app.post("/projects/{slug}/runs/{run_id}/cancel")
async def cancel_run(slug: str, run_id: str):
    if not store.get_run(slug, run_id):
        raise HTTPException(404)
    synthesizer.cancel(run_id)
    store.update_status(slug, run_id, state="stopped")
    return RedirectResponse(f"/projects/{slug}", status_code=303)


@app.post("/projects/{slug}/runs/{run_id}/resume")
async def resume_run(slug: str, run_id: str):
    run = store.get_run(slug, run_id)
    if not run or run.status.get("state") != "stopped":
        raise HTTPException(400)
    run_dir = store.PROJECTS_DIR / slug / "runs" / run_id
    await synthesizer.launch(run_dir, run.settings, run_id)
    return RedirectResponse(f"/projects/{slug}", status_code=303)


def main():
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "info"))
    args, _ = parser.parse_known_args()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web.app:app", host=host, port=port, reload=True, log_level=args.log_level)


@app.post("/projects/{slug}/runs/{run_id}/delete")
async def delete_run(slug: str, run_id: str):
    run = store.get_run(slug, run_id)
    if not run:
        raise HTTPException(404)
    if run.status.get("state") in ("running", "pending"):
        raise HTTPException(400, "Cannot delete a running run — stop it first")
    store.delete_run(slug, run_id)
    return RedirectResponse(f"/projects/{slug}", status_code=303)
