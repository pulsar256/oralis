# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Oralis Studio** is an end-user text-to-speech application powered by the VibeVoice-Realtime-0.5B model. It provides a TTS CLI, a text preprocessing CLI, and a FastAPI web UI.

## Installation

```bash
uv sync --extra rocm   # AMD GPU (ROCm 6.4, Linux only)
uv sync --extra cuda   # NVIDIA GPU
uv sync --extra mps    # Apple Silicon
uv sync --extra cpu    # CPU only (slow)

# Add streaming TTS support to any of the above:
uv sync --extra rocm --extra streamingtts

pip install flash-attn --no-build-isolation  # optional: Flash Attention
```

`transformers>=4.51.3,<5.0.0` is a hard constraint — the streaming processor depends on specific internal Transformers APIs.

## TTS CLI

`oralis` is the TTS console script (entry point from `oralis.py`):

```bash
uv run oralis "Hello World"
uv run oralis --input script.txt --speaker en-breeze_woman --output speech.wav
echo "Good morning" | uv run oralis
uv run oralis --list-voices          # shows all preset names
```

Flags: `--speaker` (default `en-breeze_woman`), `--output` (default `output.wav`), `--model`, `--device` (auto-detected), `--cfg-scale` (default 1.5), `--max-tokens` (default 512), `--list-voices`, `--seed` (optional int; omit for non-deterministic). Input priority: positional arg → `--input FILE` → stdin.

Output files are always written as `<base>_00001.wav`, `<base>_00002.wav`, … (one per chunk). For single-sentence input this produces one file named `output_00001.wav` by default.

After all chunks complete, the script concatenates them into `args.output` (e.g. `output.wav`) using stdlib `wave`; chunk files are kept. Single-chunk runs skip concatenation.

Resume is automatic: if a numbered chunk file already exists, that chunk is skipped; synthesis resumes from the first missing file. To re-synthesize a chunk, delete its `.wav` manually.

Chunk token budget (`--max-tokens`) can be exceeded by up to 2× to avoid mid-sentence splits — the packing loop extends until it lands on `.` or hits the 2× hard cap.

Each chunk prints elapsed synthesis time and a rolling-average ETA for remaining chunks.

## Text Preprocessing Utility

`preprocess-text` is the text normalization console script (entry point from `preprocess_text.py`). Normalizes Unicode punctuation, whitespace, German abbreviations, and dotted section numbers. Also strips Markdown/code/HTML formatting. Can be used standalone or imported:

```bash
uv run preprocess-text "„Hallo – Welt""   # prints: "Hallo - Welt"
uv run preprocess-text --input article.txt
echo "Guten Morgen" | uv run preprocess-text
```

```python
from preprocess_text import normalize_text
text = normalize_text(raw_text)
```

**Abbreviation expansion:** `config/abbr.json` maps German abbreviations to their spoken form (e.g. `Abb.` → `Abbildung`, `z. B.` → `zum Beispiel`). If the file is absent, expansion is silently skipped. Edit `config/abbr.json` to add, remove, or override entries — no code changes required.

**Section number expansion:** Dotted section numbers with 1–2-digit segments and 2–3 parts are expanded to German words (e.g. `1.1` → `eins punkt eins`, `11.3.2` → `elf punkt drei punkt zwei`). IP addresses and longer dotted sequences are protected by lookbehind/lookahead guards.

**Formatting strip (`--strip-formatting`):** Removes Markdown fences (keeps block content), inline code backticks, HTML tags, URLs, headers, bold/italic markers, tables, blockquotes, list markers, and square brackets. Runs before Unicode normalization. Enabled by default in the web UI (`strip_formatting` in `KNOWN_STEPS`).

## Web UI

```bash
bash studio.sh
# or: HOST=0.0.0.0 PORT=9000 bash studio.sh
```

FastAPI + HTMX + SSE. Source in `web/`:
- `app.py` — routes, SSE progress streaming, voice discovery via `oralis --list-voices`
- `synthesizer.py` — subprocess launcher for `oralis`, tqdm progress extraction
- `preprocessor.py` — wraps `preprocess_text` module, diff visualization
- `project_store.py` — project/run state persistence

## Tests

```bash
uv run pytest
```

## Architecture

### TTS Data Flow

```
Text → TextTokenizer → Qwen2.5-1.5B (streaming) → SemanticTokenizer latents → DiffusionHead (DPM-Solver) → AcousticDecoder → 24kHz waveform
```

### Key Modules

| Directory | Purpose |
|-----------|---------|
| `oralis_studio/modular/` | Streaming TTS model, tokenizers, diffusion head |
| `oralis_studio/processor/` | Audio/text preprocessing pipelines |
| `oralis_studio/schedule/` | Diffusion timestep sampling and DPM-Solver |
| `oralis_studio/configs/` | JSON model configs (Qwen2.5-1.5B) |
| `voices/` | Voice preset `.pt` files for Realtime-0.5B |
| `config/` | Application config (abbreviation maps, future language configs) |
| `web/` | FastAPI web UI |

### Tokenizer Design

`AcousticTokenizer` and `SemanticTokenizer` (in `oralis_studio/modular/modular_vibevoice_tokenizer.py`) are VAE-based with:
- Depthwise convolutional mixer encoders/decoders
- RMSNorm throughout
- VAE standardization (mean/std normalization of latents)
- Operates at 7.5 Hz frame rate (extreme downsampling for long-context efficiency)

### Voice Presets

`.pt` files in `voices/` are cached model states for **Realtime-0.5B only**. Default: `en-breeze_woman`. Multi-lingual presets available (de, en, fr, etc.). Experimental voices (~144 MB) are gitignored — run `bash download_experimental_voices.sh` from the repo root to fetch them into `voices/experimental_voices/`.

### Model Configuration

`oralis_studio/configs/qwen2.5_1.5b_64k.json` — Realtime TTS (64K context, Qwen2.5-1.5B)

Config is nested: `acoustic_tokenizer_config`, `semantic_tokenizer_config`, `decoder_config`, `diffusion_head_config`.

## Contribution Guidelines

- Keep code minimal and readable; avoid unnecessary abstraction
- All changes are reviewed line-by-line
- Large LLM-generated code blocks will be rejected unless rigorously verified
- Style-only PRs are rejected
- All documentation, comments, and commit messages must be in English
