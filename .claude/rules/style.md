# Style Rules

- Language: Python 3.10+; package manager: `uv`
- Keep code minimal and readable — avoid unnecessary abstraction
- No speculative abstractions or helpers for one-time operations
- Do not add docstrings, comments, or type annotations to unchanged code
- Comments only where logic is non-obvious
- All docs, comments, and commit messages in English
- Hard constraint: `transformers>=4.51.3,<5.0.0` — do not relax or remove
- GPU extras are mutually exclusive (`rocm`, `cuda`, `mps`, `cpu`) — keep conflicts declaration in pyproject.toml
