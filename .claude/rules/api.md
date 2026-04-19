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
