from __future__ import annotations
import difflib
import html as _html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from preprocess_text import normalize_text

KNOWN_STEPS: list[dict] = [
    {"id": "strip_formatting",       "label": "Strip formatting"},
    {"id": "normalize_unicode",      "label": "Normalize Unicode"},
    {"id": "expand_abbreviations",   "label": "Expand abbreviations"},
    {"id": "expand_section_numbers", "label": "Expand section numbers"},
]


def apply_steps(text: str, steps: list[dict]) -> str:
    enabled = {s["id"] for s in steps if s.get("enabled")}
    if not enabled:
        return text
    return normalize_text(
        text,
        strip_fmt="strip_formatting" in enabled,
        expand_abbr="expand_abbreviations" in enabled,
        expand_numbers="expand_section_numbers" in enabled,
    )


def diff_html(original: str, transformed: str) -> str:
    orig_words = original.split()
    new_words = transformed.split()
    matcher = difflib.SequenceMatcher(None, orig_words, new_words, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            parts.append(_html.escape(" ".join(orig_words[i1:i2])))
        elif tag == "replace":
            parts.append(f'<del>{_html.escape(" ".join(orig_words[i1:i2]))}</del>')
            parts.append(f'<ins>{_html.escape(" ".join(new_words[j1:j2]))}</ins>')
        elif tag == "delete":
            parts.append(f'<del>{_html.escape(" ".join(orig_words[i1:i2]))}</del>')
        elif tag == "insert":
            parts.append(f'<ins>{_html.escape(" ".join(new_words[j1:j2]))}</ins>')
    return " ".join(parts)


def preview(text: str, steps: list[dict], max_chars: int = 300) -> str:
    if len(text) > max_chars:
        cutoff = text.rfind(" ", 0, max_chars)
        snippet = text[: cutoff if cutoff > 0 else max_chars]
    else:
        snippet = text
    return diff_html(snippet, apply_steps(snippet, steps))


def full_diff(text: str, steps: list[dict]) -> str:
    return diff_html(text, apply_steps(text, steps))


def default_steps() -> list[dict]:
    return [
        {"id": s["id"], "label": s["label"], "enabled": s["id"] in ("normalize_unicode", "strip_formatting")}
        for s in KNOWN_STEPS
    ]
