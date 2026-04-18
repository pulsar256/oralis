#!/usr/bin/env python3
"""Text normalization utility — normalize Unicode punctuation and whitespace.

Usage:
    uv run preprocess-text "Hallo – Welt"
    uv run preprocess-text --input article.txt
    echo "Guten Morgen" | uv run preprocess-text
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


_ONES = [
    "null", "eins", "zwei", "drei", "vier", "fünf",
    "sechs", "sieben", "acht", "neun", "zehn", "elf",
    "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn",
    "siebzehn", "achtzehn", "neunzehn",
]
_COMPOUND_ONES = [
    "null", "ein", "zwei", "drei", "vier", "fünf",
    "sechs", "sieben", "acht", "neun",
]
_TENS = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig",
         "sechzig", "siebzig", "achtzig", "neunzig"]


def _int_to_german(n: int) -> str:
    """Convert an integer 0–99 to a German word; fall back to str() outside that range."""
    if n < 0 or n > 99:
        return str(n)
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _TENS[tens]
    return f"{_COMPOUND_ONES[ones]}und{_TENS[tens]}"


def expand_section_numbers(text: str) -> str:
    """Replace dotted section numbers (e.g. 1.1, 11.3.2) with German words.

    Matches 1–2-digit segments with 2–3 total parts.
    Lookbehind/lookahead (?<![.\\d]) / (?![.\\d]) prevent matching sub-sequences
    of longer dotted strings such as IP addresses.
    """
    def _replace(m: re.Match) -> str:
        return " punkt ".join(_int_to_german(int(s)) for s in m.group(1).split("."))

    return re.sub(r'(?<![.\d])\b(\d{1,2}(?:\.\d{1,2}){1,2})\b(?![.\d])', _replace, text)


def _load_abbr_map(path: Path | None = None) -> dict[str, str]:
    """Load abbreviation map from a JSON file. Returns {} if file is absent."""
    if path is None:
        path = Path(__file__).parent / "config" / "abbr.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def expand_abbreviations(text: str, abbr_map: dict[str, str]) -> str:
    """Expand German abbreviations, skipping sentence-final positions.

    Abbreviations are matched longest-first. An abbreviation ending in '.' is
    skipped when followed by whitespace + an uppercase letter or by a newline,
    which indicates sentence-final position.
    """
    if not abbr_map:
        return text
    for abbr, expansion in sorted(abbr_map.items(), key=lambda x: -len(x[0])):
        escaped = re.escape(abbr)
        # (?<!\w) — do not match inside a longer word
        # (?!\s+[A-ZÄÖÜ]) — skip if uppercase word follows (sentence-final)
        # (?!\s*\n) — skip if newline follows (paragraph break)
        pattern = rf'(?<!\w){escaped}(?!\s+[A-ZÄÖÜ])(?!\s*\n)'
        text = re.sub(pattern, expansion, text)
    return text


_ABBR_MAP = _load_abbr_map()


def strip_formatting(text: str) -> str:
    """Remove markup and non-readable formatting characters that confuse TTS.

    Strips fenced code blocks, inline code, HTML tags, URLs, and Markdown
    decoration (headers, bold/italic, tables, blockquotes, list markers).
    Readable text content is preserved.
    """
    # Fenced code blocks — strip the fence lines, keep the content
    text = re.sub(r'(?:```|~~~)[^\n]*\n([\s\S]*?)(?:```|~~~)', r'\1', text)
    # Inline code — strip backticks, keep the text
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    # HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Markdown images — keep alt text (before URL stripping)
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Markdown links — keep link text, drop URL (before URL stripping)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remaining square brackets (reference links, footnotes, etc.) — keep content
    text = re.sub(r'\[([^\]]*)\]', r'\1', text)
    # Bare URLs
    text = re.sub(r'https?://\S+', '', text)
    # Markdown headers — remove leading # symbols, keep the heading text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Bold / italic markers — remove decoration, keep inner text
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', text)
    # Blockquote markers
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # Table rows (lines made of |, -, :, space) and separator lines
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-|: ]{3,}$', '', text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Unordered list markers
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Ordered list markers
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Collapse runs of blank lines left by removed blocks
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def normalize_text(text: str, expand_abbr: bool = False, expand_numbers: bool = False,
                   strip_fmt: bool = False) -> str:
    """Normalize Unicode punctuation and whitespace."""
    if strip_fmt:
        text = strip_formatting(text)
    text = (
        text
        # BOM
        .replace("\ufeff", "")
        # Curly / typographic quotes → ASCII
        .replace("\u2018", "'")   # left single quotation mark
        .replace("\u2019", "'")   # right single quotation mark
        .replace("\u201a", "'")   # single low-9 quotation mark (German ‚)
        .replace("\u201c", '"')   # left double quotation mark
        .replace("\u201d", '"')   # right double quotation mark
        .replace("\u201e", '"')   # double low-9 quotation mark (German „)
        # Non-breaking / narrow / typographic spaces → regular space
        .replace("\u00a0", " ")   # no-break space
        .replace("\u202f", " ")   # narrow no-break space
        .replace("\u2009", " ")   # thin space
        .replace("\u2002", " ")   # en space
        .replace("\u2003", " ")   # em space
        # Non-breaking hyphen → regular hyphen
        .replace("\u2010", "-")
        # En dash → spaced hyphen (common in German prose)
        .replace("\u2013", " - ")
        # Ellipsis → three dots
        .replace("\u2026", "...")
        # Bullet + tab at line start → strip, keep text
        .replace("\u2022\t", "")
        .replace("\u2022", "")
        # Tabs → space
        .replace("\t", " ")
    )
    # De-hyphenate: join words split across lines by a justified-text hyphen.
    # Lowercase continuation → remove hyphen ("wer-\nden" → "werden")
    # Uppercase continuation → keep hyphen ("Change-\nManagement" → "Change-Management")
    text = re.sub(
        r'([a-zA-ZäöüÄÖÜß])-\n([a-zA-ZäöüÄÖÜß])',
        lambda m: m.group(1) + (m.group(2) if m.group(2).islower() else '-' + m.group(2)),
        text,
    )
    # Join wrapped lines within a paragraph into a single line.
    # Paragraph breaks (2+ newlines) are preserved; lone newlines become spaces.
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Trim each paragraph and normalise paragraph separators to exactly \n\n.
    text = '\n\n'.join(p.strip() for p in re.split(r'\n{2,}', text))
    if expand_abbr:
        text = expand_abbreviations(text, _ABBR_MAP)
    if expand_numbers:
        text = expand_section_numbers(text)
    return text


def resolve_text(args: argparse.Namespace) -> str:
    """Return text from positional arg, --input file, or stdin."""
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
        description="Normalize Unicode punctuation and whitespace in text."
    )
    parser.add_argument("text", nargs="?", help="Text to normalize")
    parser.add_argument("-i", "--input", metavar="FILE", help="Path to a .txt file")
    parser.add_argument("-o", "--output", metavar="FILE", help="Write result to FILE instead of stdout")
    parser.add_argument(
        "--expand-abbreviations", action="store_true",
        help="Expand German abbreviations (e.g. Abb. → Abbildung)",
    )
    parser.add_argument(
        "--expand-section-numbers", action="store_true",
        help="Expand dotted section numbers (e.g. 1.1 → eins punkt eins)",
    )
    parser.add_argument(
        "--strip-formatting", action="store_true",
        help="Strip Markdown, code blocks, HTML tags, and URLs before normalizing",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    text = resolve_text(args)
    result = normalize_text(
        text,
        expand_abbr=args.expand_abbreviations,
        expand_numbers=args.expand_section_numbers,
        strip_fmt=args.strip_formatting,
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            print(result, file=f)
    else:
        print(result)


if __name__ == "__main__":
    main()
