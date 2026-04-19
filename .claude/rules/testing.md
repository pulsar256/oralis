# Testing Rules

- Runner: `uv run pytest` (asyncio_mode = auto)
- Dev deps: `pytest-asyncio`
- Test files live in `tests/`; naming: `test_<module>.py`
- Hardware: Always include `--extra rocm` with `uv run` for testing (e.g. `uv run --extra rocm pytest`).
- No mocking of internal model/tokenizer internals — test behavior, not implementation
- Do not add tests for trivial getters; cover logic branches and edge cases
- Run the full suite before marking any task complete
