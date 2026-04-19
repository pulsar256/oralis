# Style Rules

- Language: Python 3.10+; package manager: `uv`
- Keep code minimal and readable — avoid unnecessary abstraction
- No speculative abstractions or helpers for one-time operations
- Do not add docstrings, comments, or type annotations to unchanged code
- Comments only where logic is non-obvious
- All docs, comments, and commit messages in English
- Hard constraint: `transformers>=4.51.3,<5.0.0` — do not relax or remove
- GPU extras are mutually exclusive (`rocm`, `cuda`, `mps`, `cpu`) — keep conflicts declaration in pyproject.toml

## UI & Client-side Conventions
- **Header Actions**: Action buttons in headers (e.g., runs) must have a fixed height of `20px` and use flexbox for vertical centering.
- **Event Naming**: Use the `oralis:<topic>-<action>` namespace for custom browser events.
- **SSE Targeting**: Always use scoped selectors with `runId` to avoid ID collisions in lists.
- **Interactive UI**: Prefer `onclick="func(id, event)"` and `event.stopPropagation()` checks inside handlers rather than blocking bubbling, to allow document-level delegation (like queuing) to work.
