# Oralis Studio

> Local-first text-to-speech for long-form reading — articles, ebooks, anything you'd rather listen to.

TL;DR: Built for personal use as an audiobook-quality "reading list" player: queue up what you couldn't read on screen, then listen while doing dishes

The primary use case and motivation to create this was the lack of local first text-to-speech tooling capable of synthesizing larger text volumes into audiobook-like quality audio files. I am using this as a "reading list" for articles on the internet and sometimes ebooks. When I do laundry, dishes, cooking and otherwise mundane tasks, I do listen to a curated set of articles I was not able to read on the screen. This is why it exists, and all features I will consider adding here will be always put into that perspective.

> [!WARNING]
> This is a personal tool, not a production service. It is mostly vibe-coded and it takes shortcuts (direct filesystem project management, no auth). Do not expose it to the public internet. Use for your pesonal amusement only.

![img_1.png](docs/img.png)

## Installation

Pick the extra that matches your hardware:

```bash
uv sync --extra rocm   # AMD GPU (ROCm 6.4, Linux only)
uv sync --extra cuda   # NVIDIA GPU
uv sync --extra mps    # Apple Silicon
uv sync --extra cpu    # CPU only (slow)
```

Requires Python ≥ 3.10.

## Studio

The web UI is the main interface. It manages projects, preprocesses text, and tracks synthesis progress.

```bash
bash studio.sh
```

Opens at `http://localhost:8000`. The script uses `UV_BACKEND` (default: `rocm`) to select the torch backend:

```bash
UV_BACKEND=cuda bash studio.sh
HOST=0.0.0.0 PORT=9000 UV_BACKEND=rocm bash studio.sh
```

**What you can do in the Studio:**

- **Projects** — create named projects, each holding source text and synthesis runs
- **Preprocessing** — normalize Unicode, expand German abbreviations, convert section numbers to spoken form — with a live diff so you see exactly what changed before committing
- **Synthesis** — pick a voice, run TTS, watch per-chunk progress in real time
- **Resume** — interrupted runs pick up from the last completed chunk automatically

## Voice Presets

`.pt` files in `voices/` define the available speakers. Run `uv run --extra rocm oralis --list-voices` to see all names.

Default voice: `en-breeze_woman`.

Additional experimental voices (multi-lingual, ~144 MB) are not bundled. Run `bash download_experimental_voices.sh` to fetch them into `voices/experimental_voices/`.

## CLI

The CLI is available for scripting and batch use outside the Studio.

```bash
uv run --extra rocm oralis "Hello World"
uv run --extra rocm oralis --input script.txt --speaker en-breeze_woman --output speech.wav
echo "Good morning" | uv run --extra rocm oralis
```

Output is written as numbered chunks (`output_00001.wav`, `output_00002.wav`, …) then concatenated into the final file. Existing chunks are skipped on re-run.

| Flag             | Default   | Effect                                                                                                                                                               |
|------------------|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--max-tokens N` | `512`     | Maximum text tokens per synthesis chunk. Smaller values use less VRAM and produce shorter audio segments; larger values may improve prosody across longer sentences. |
| `--cfg-scale F`  | `1.5`     | Classifier-free guidance strength. Higher values make the output follow the text more strictly but can reduce naturalness; lower values sound more relaxed.          |
| `--seed N`       | *(unset)* | Fixed seed for reproducible output. Omit for non-deterministic synthesis.                                                                                            |

Text preprocessing is also available standalone:

```bash
uv run --extra rocm preprocess-text --input article.txt
echo "z. B. Abb. 1.1" | uv run --extra rocm preprocess-text
```

Edit `config/abbr.json` to add or override German abbreviation expansions — no code changes needed.

## License

See [LICENSE](LICENSE). VibeVoice model weights are subject to the [Microsoft Research License](https://github.com/microsoft/VibeVoice).

Powered by [VibeVoice-Realtime-0.5B](https://github.com/microsoft/VibeVoice).
