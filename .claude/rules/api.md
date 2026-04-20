# Web / API Rules

- Framework: FastAPI + HTMX + SSE (no heavy JS frontend)
- Routes and SSE in `web/app.py`; subprocess logic in `web/synthesizer.py`
- Preprocessing wrapper in `web/preprocessor.py`; state in `web/project_store.py`
- Voice list is discovered at runtime via `oralis --list-voices` subprocess call
- Progress is extracted from tqdm output in the synthesizer subprocess
- Do not add REST endpoints for things that can be done via CLI subprocess calls
- Strip formatting is enabled by default in the web UI (`strip_formatting` in `KNOWN_STEPS`)

- `app.js` is loaded with `defer` — inline `<script>` tags in Jinja2 partials run before it.
  To call a deferred function from a partial, guard with readyState:
  `if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', go); } else { go(); }`
  (`DOMContentLoaded` fires after deferred scripts; the `else` branch handles HTMX swaps where the event already fired)

- Always use `| tojson` when interpolating Jinja2 variables into a JS context inside `<script>` tags

- HTMX: when `hx-target` and `hx-select` point to the same element ID, add `hx-swap="outerHTML"`,
  otherwise the selected element gets nested inside the target instead of replacing it

- To reset an `<audio>` element cleanly: `audio.removeAttribute('src'); audio.load()`
  (`audio.src = ''` causes a spurious network error in the console)

- All state-mutating forms (create run, stop, resume, delete) use HTMX partial swap:
  `hx-post="..." hx-target="#main" hx-select="#main" hx-swap="outerHTML"`.
  The player bar lives outside `#main` in `base.html` and survives all swaps.

- Dynamically-created elements with `hx-*` attributes need `htmx.process(el)` after
  appending to the DOM, or HTMX will not register them.

- Simple state saves (rename, etc.) that don't require a page re-render should use a
  plain `fetch()` POST returning 204, not HTMX. Update the DOM in JS directly.

- Audio is served via two URL patterns: chunk files at `.../files/{filename}` and the
  final concatenated output at `.../download`. Any feature handling audio (waveform,
  download, etc.) must implement both routes — they resolve to different files on disk.

- CPU/IO-bound work in FastAPI routes runs in a thread executor to avoid blocking the
  event loop: `await asyncio.get_running_loop().run_in_executor(None, fn)`

- EventSource `onerror` must be a no-op (`es.onerror = () => {}`). The `done` handler
  calls `es.close()` to prevent reconnects after success. Calling `es.close()` in `onerror`
  permanently kills the stream before the buffered `done` event is dispatched — a race on
  clean server close that leaves the UI stuck in the last known state.

- `htmx:beforeSwap` must guard on the swap target before closing SSE streams:
  `if (e.detail.target?.id !== 'main') return;`
  Any targeted HTMX swap (e.g. `hx-target="#full-text-body"`) fires the same event and
  would otherwise kill all active synthesis streams.

- In `stream_chunks`, do not add a wav to `seen` or emit a `chunk` event until its sibling
  `.txt` file exists. Read the txt in the same poll cycle it appears; defer to the next poll
  if it is missing. This prevents empty snippet fields caused by detecting the wav before
  the txt write completes.
