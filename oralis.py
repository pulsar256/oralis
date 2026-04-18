#!/usr/bin/env python3
"""Oralis Studio — TTS console application.

Usage:
    uv run oralis "Hello World"
    uv run oralis --input script.txt --speaker en-breeze_woman --output speech.wav
    echo "Good morning" | uv run oralis
"""

import argparse
import copy
import glob
import json
import os
import re
import sys
import time
import traceback
import wave

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch


class VoiceMapper:
    """Maps speaker names to .pt voice file paths under voices/."""

    def __init__(self):
        voices_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "voices",
        )
        if not os.path.exists(voices_dir):
            print(
                f"Warning: voices directory not found at {voices_dir}", file=sys.stderr
            )
            self._presets: dict[str, str] = {}
            return
        self._presets = dict(
            sorted(
                {
                    os.path.splitext(os.path.basename(p))[0].lower(): os.path.abspath(p)
                    for p in glob.glob(
                        os.path.join(voices_dir, "**", "*.pt"), recursive=True
                    )
                }.items()
            )
        )

    def list_voices(self) -> list[str]:
        return list(self._presets.keys())

    def get_voice_path(self, speaker_name: str) -> str:
        """Return .pt path for speaker_name. Supports partial/case-insensitive match."""
        if not speaker_name:
            print("Error: --speaker cannot be empty.", file=sys.stderr)
            sys.exit(1)
        key = speaker_name.lower()
        if key in self._presets:
            return self._presets[key]
        matches = [p for name, p in self._presets.items() if key in name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(
                f"Error: '{speaker_name}' matches multiple voices: "
                + ", ".join(n for n in self._presets if key in n)
                + ". Be more specific.",
                file=sys.stderr,
            )
            sys.exit(1)
        # Fallback to first preset
        if not self._presets:
            print("Error: no voices available.", file=sys.stderr)
            sys.exit(1)
        fallback_name = next(iter(self._presets))
        print(
            f"Warning: no voice found for '{speaker_name}', using {fallback_name}",
            file=sys.stderr,
        )
        return self._presets[fallback_name]


def _write_progress(path: str | None, data: dict) -> None:
    if not path:
        return
    existing = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    existing.update(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f)


def _count_tokens(text: str, tokenizer) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def split_into_chunks(text: str, tokenizer, max_tokens: int) -> list[str]:
    """Split text into chunks each containing at most max_tokens text tokens.

    Steps:
    1. Collapse blank lines so paragraphs are separated by a single newline.
    2. Split on newlines to get paragraphs.
    3. Greedily pack paragraphs into chunks; overflow paragraphs are split at
       sentence boundaries ('. '); sentences that still overflow are emitted as
       their own chunk with a warning.
    """
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # rejoin hyphenated line breaks
    paragraphs_raw = re.split(r"\n{2,}", text)              # split on blank lines only
    paragraphs = [re.sub(r"\n", " ", p).strip()             # join soft wraps within paragraph
                  for p in paragraphs_raw if p.strip()]

    units: list[str] = []
    for para in paragraphs:
        if _count_tokens(para, tokenizer) <= max_tokens:
            units.append(para)
        else:
            # Split oversized paragraph into sentences
            sentences = [s.strip() for s in para.split(". ") if s.strip()]
            for j, sent in enumerate(sentences):
                # Re-add the period we split on (except for the last fragment)
                piece = (
                    sent
                    if sent.endswith(".") or j == len(sentences) - 1
                    else sent + "."
                )
                if _count_tokens(piece, tokenizer) > max_tokens:
                    print(
                        f"Warning: sentence exceeds --max-tokens ({_count_tokens(piece, tokenizer)} tokens); "
                        "emitting as oversized chunk.",
                        file=sys.stderr,
                    )
                units.append(piece)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = _count_tokens(unit, tokenizer)
        if current_parts and current_tokens + unit_tokens > max_tokens:
            # Flush immediately if we already land on a sentence boundary, or
            # if adding this unit would push us past twice the budget.
            ends_sentence = current_parts[-1].rstrip().endswith(".")
            within_double = current_tokens + unit_tokens <= max_tokens * 2
            if ends_sentence or not within_double:
                chunks.append(" ".join(current_parts))
                current_parts = [unit]
                current_tokens = unit_tokens
            else:
                # Over budget but extend to avoid a mid-sentence split.
                current_parts.append(unit)
                current_tokens += unit_tokens
        else:
            current_parts.append(unit)
            current_tokens += unit_tokens

    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


_SUPPORTED_MODELS = ("realtime-0.5b",)


def _check_model_supported(model_path: str) -> None:
    name = model_path.lower().rstrip("/").split("/")[-1]
    if not any(tag in name for tag in _SUPPORTED_MODELS):
        print(
            f"Error: '{model_path}' is not supported by this script.\n"
            "oralis.py only works with VibeVoice-Realtime-0.5B.\n"
            "VibeVoice-TTS-1.5B has been disabled and its code removed from this repo.",
            file=sys.stderr,
        )
        sys.exit(1)


def load_model(model_path: str, device: str):
    from oralis_studio.modular.modeling_vibevoice_streaming_inference import (
        VibeVoiceStreamingForConditionalGenerationInference,
    )

    if device == "mps":
        load_dtype = torch.float32
        attn_impl = "sdpa"
    elif device == "cuda":
        is_rocm = torch.version.hip is not None
        load_dtype = torch.float32 if is_rocm else torch.bfloat16
        attn_impl = "sdpa" if is_rocm else "flash_attention_2"
    else:
        load_dtype = torch.float32
        attn_impl = "sdpa"

    print(
        f"Loading model from {model_path} (dtype={load_dtype}, attn={attn_impl}, device={device})"
    )
    try:
        if device == "mps":
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                attn_implementation=attn_impl,
                device_map=None,
            )
            model.to("mps")
        else:
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=device,
                attn_implementation=attn_impl,
            )
    except Exception as e:
        if attn_impl == "flash_attention_2":
            print(
                f"[WARN] flash_attention_2 failed ({type(e).__name__}), retrying with sdpa",
                file=sys.stderr,
            )
            print(traceback.format_exc(), file=sys.stderr)
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=device,
                attn_implementation="sdpa",
            )
        else:
            raise

    model.eval()
    model.set_ddpm_inference_steps(num_steps=5)
    return model


def resolve_text(args: argparse.Namespace) -> str:
    """Return text from positional arg, --input file, or stdin. Exits on error."""
    if args.text:
        return args.text
    if args.input:
        if not os.path.exists(args.input):
            print(f"Error: input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input, encoding="utf-8") as f:
            return f.read().strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    print(
        "Error: provide text as argument, --input FILE, or via stdin.", file=sys.stderr
    )
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VibeVoice Realtime-0.5B TTS — synthesize speech from text."
    )
    parser.add_argument("text", nargs="?", help="Text to synthesize")
    parser.add_argument("-i", "--input", metavar="FILE", help="Path to a .txt file")
    parser.add_argument(
        "-o", "--output",
        default="output.wav",
        metavar="PATH",
        help="Output WAV path (default: output.wav)",
    )
    parser.add_argument(
        "--speaker",
        default="en-breeze_woman",
        metavar="NAME",
        help="Voice preset name (default: en-breeze_woman)",
    )
    parser.add_argument(
        "--model",
        default="microsoft/VibeVoice-Realtime-0.5B",
        metavar="MODEL",
        help="HuggingFace model path or local dir",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Device: cuda | rocm | hip | mps | cpu (auto-detected by default); rocm/hip are aliases for cuda",
    )
    parser.add_argument(
        "--cfg-scale",
        type=float,
        default=1.5,
        dest="cfg_scale",
        help="Classifier-free guidance scale (default: 1.5). Higher values follow the text more strictly; lower values sound more natural but increase the risk of audio artifacts.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        dest="max_tokens",
        metavar="N",
        help="Max text tokens per synthesis chunk (default: 512)",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print available voice preset names and exit",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="N",
        help="Random seed for deterministic synthesis (default: non-deterministic)",
    )
    parser.add_argument(
        "--progress-file",
        metavar="PATH",
        default=None,
        dest="progress_file",
        help="JSON file to write chunk_count and current_chunk during synthesis",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    voice_mapper = VoiceMapper()

    if args.list_voices:
        for name in voice_mapper.list_voices():
            print(name)
        sys.exit(0)

    from oralis_studio.processor.vibevoice_streaming_processor import (
        VibeVoiceStreamingProcessor,
    )

    text = resolve_text(args)

    if not text:
        print("Error: text is empty after reading input.", file=sys.stderr)
        sys.exit(1)

    device = args.device
    # Normalize device string
    if device == "mpx":
        device = "mps"
    if device in ("rocm", "hip"):
        device = "cuda"
    if device == "cuda" and not torch.cuda.is_available():
        print(
            "Warning: CUDA/ROCm device not available, falling back to CPU.",
            file=sys.stderr,
        )
        device = "cpu"
    if device == "auto":
        device = (
            "cuda"
            if torch.cuda.is_available()
            else ("mps" if torch.backends.mps.is_available() else "cpu")
        )
    # Final MPS safety check regardless of how device was resolved
    if device == "mps" and not torch.backends.mps.is_available():
        print("Warning: MPS not available, falling back to CPU.", file=sys.stderr)
        device = "cpu"

    voice_path = voice_mapper.get_voice_path(args.speaker)
    print(f"Voice: {args.speaker}  ({voice_path})")
    if device == "cuda":
        if torch.version.hip is not None:
            backend_info = f"ROCm/HIP {torch.version.hip}"
        else:
            backend_info = f"CUDA {torch.version.cuda}"
        device_str = f"{device} ({backend_info})"
    else:
        device_str = device
    print(
        f"Output: {args.output}  |  Device: {device_str}  |  CFG scale: {args.cfg_scale}"
    )

    processor = VibeVoiceStreamingProcessor.from_pretrained(args.model)

    chunks = split_into_chunks(text, processor.tokenizer, args.max_tokens)
    _write_progress(args.progress_file, {"chunk_count": len(chunks), "current_chunk": 0})
    print(f"Chunks: {len(chunks)}")

    if args.seed is not None:
        torch.manual_seed(args.seed)
        if device == "cuda":
            torch.cuda.manual_seed_all(args.seed)
        print(f"Seed: {args.seed}")

    output_base = (
        args.output[:-4] if args.output.lower().endswith(".wav") else args.output
    )

    _check_model_supported(args.model)
    model = load_model(args.model, device)
    all_prefilled_outputs = torch.load(
        voice_path, map_location=device, weights_only=False
    )

    chunk_times: list[float] = []

    def _fmt_seconds(s: float) -> str:
        return f"{int(s // 60)} min {int(s % 60)} s" if s >= 60 else f"{int(s)} s"

    for i, chunk in enumerate(chunks, 1):
        output_path = f"{output_base}_{i:05d}.wav"
        text_path = f"{output_base}_{i:05d}.txt"
        if os.path.exists(output_path):
            print(f"[{i}/{len(chunks)}] Skipping {output_path} (already exists)")
            _write_progress(args.progress_file, {"current_chunk": i})
            continue
        print(f"\n[{i}/{len(chunks)}] {output_path}")

        _write_progress(args.progress_file, {"current_chunk": i})

        inputs = processor.process_input_with_cached_prompt(
            text=chunk,
            cached_prompt=copy.deepcopy(all_prefilled_outputs),
            padding=True,
            return_tensors="pt",
            return_attention_mask=True,
        )
        for k, v in inputs.items():
            if torch.is_tensor(v):
                inputs[k] = v.to(device)

        print("Generating audio…")
        t0 = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=None,
                cfg_scale=args.cfg_scale,
                tokenizer=processor.tokenizer,
                generation_config={"do_sample": False},
                verbose=True,
                all_prefilled_outputs=copy.deepcopy(all_prefilled_outputs),
            )

        if not outputs.speech_outputs or outputs.speech_outputs[0] is None:
            print(f"Error: model produced no audio for chunk {i}.", file=sys.stderr)
            continue

        elapsed = time.time() - t0
        chunk_times.append(elapsed)

        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)
        processor.save_audio(outputs.speech_outputs[0], output_path=output_path)
        with open(text_path, "w", encoding="utf-8") as tf:
            tf.write(chunk)

        remaining = len(chunks) - i
        if remaining > 0 and chunk_times:
            avg = sum(chunk_times) / len(chunk_times)
            eta_str = f"  ETA: ~{_fmt_seconds(avg * remaining)}"
        else:
            eta_str = ""
        print(f"Saved: {output_path}  ({_fmt_seconds(elapsed)}{eta_str})")

    _write_progress(args.progress_file, {"current_chunk": len(chunks)})

    chunk_paths = [
        f"{output_base}_{i:05d}.wav"
        for i in range(1, len(chunks) + 1)
        if os.path.exists(f"{output_base}_{i:05d}.wav")
    ]
    if len(chunk_paths) > 1:
        print(f"\nConcatenating {len(chunk_paths)} chunks → {args.output}")
        with wave.open(args.output, "wb") as out:
            for j, path in enumerate(chunk_paths):
                with wave.open(path, "rb") as w:
                    if j == 0:
                        out.setparams(w.getparams())
                    out.writeframes(w.readframes(w.getnframes()))
        print(f"Saved: {args.output}")
    elif len(chunk_paths) == 1:
        # Single chunk — the numbered file is the only output, nothing to join.
        pass


if __name__ == "__main__":
    main()
