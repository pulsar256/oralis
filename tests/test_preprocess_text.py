"""Tests for preprocess_text normalization functions."""
import subprocess
import sys
from pathlib import Path

from preprocess_text import expand_abbreviations, expand_section_numbers, _load_abbr_map, normalize_text


class TestExpandSectionNumbers:
    def test_two_part(self):
        assert expand_section_numbers("1.1") == "eins punkt eins"

    def test_three_part(self):
        assert expand_section_numbers("1.1.2") == "eins punkt eins punkt zwei"

    def test_two_digit_segment(self):
        assert expand_section_numbers("11.3.2") == "elf punkt drei punkt zwei"

    def test_embedded_in_text(self):
        assert expand_section_numbers("siehe Abschn. 1.1 oben") == "siehe Abschn. eins punkt eins oben"

    def test_ip_address_unchanged(self):
        # lookbehind (?<![.\d]) fires on the "." before the tail "1.1"
        assert expand_section_numbers("192.168.1.1") == "192.168.1.1"

    def test_four_part_unchanged(self):
        # lookahead (?![.\d]) fires on ".1" after the matched "1.1.1"
        assert expand_section_numbers("1.1.1.1") == "1.1.1.1"

    def test_no_match_plain_text(self):
        assert expand_section_numbers("Hallo Welt") == "Hallo Welt"

    def test_twentyone(self):
        assert expand_section_numbers("21.3") == "einundzwanzig punkt drei"

    def test_zero_segment(self):
        assert expand_section_numbers("0.1") == "null punkt eins"

    def test_version_number_expanded(self):
        # Dotted numbers within \d{1,2} bounds always expand — this includes version numbers
        # and decimal fractions (e.g. 3.14 → "drei punkt vierzehn"). Full decimal handling
        # is out of scope; in German text, decimals normally use a comma, not a period.
        assert expand_section_numbers("Version 2.0") == "Version zwei punkt null"

    def test_letter_prefix_unchanged(self):
        # \b does not fire between a letter and a digit, so "v1.2" is unchanged
        assert expand_section_numbers("v1.2") == "v1.2"


class TestLoadAbbrMap:
    def test_loads_valid_json(self, tmp_path):
        f = tmp_path / "abbr.json"
        f.write_text('{"Abb.": "Abbildung"}', encoding="utf-8")
        result = _load_abbr_map(f)
        assert result == {"Abb.": "Abbildung"}

    def test_missing_file_returns_empty(self, tmp_path):
        result = _load_abbr_map(tmp_path / "nonexistent.json")
        assert result == {}


class TestExpandAbbreviations:
    ABBR = {
        "Abb.": "Abbildung",
        "Abschn.": "Abschnitt",
        "z. B.": "zum Beispiel",
        "ca.": "circa",
        "s.": "siehe",
    }

    def test_basic_expansion(self):
        assert expand_abbreviations("Abb. 3 zeigt", self.ABBR) == "Abbildung 3 zeigt"

    def test_longer_match_wins(self):
        # Abschn. expands in full; s. in separate position (lowercase follows) also expands
        abbr = {"Abschn.": "Abschnitt", "s.": "siehe"}
        result = expand_abbreviations("Abschn. 3 und s. unten", abbr)
        assert result == "Abschnitt 3 und siehe unten"

    def test_s_not_matched_inside_longer_word(self):
        # (?<!\w) prevents s. from firing inside Abschn.
        abbr = {"Abschn.": "Abschnitt", "s.": "siehe"}
        result = expand_abbreviations("Abschn. 3", abbr)
        assert result == "Abschnitt 3"

    def test_multiword_abbreviation(self):
        assert expand_abbreviations("z. B. ein Test", self.ABBR) == "zum Beispiel ein Test"

    def test_sentence_final_skipped_uppercase_follows(self):
        # "ca." followed by whitespace + uppercase → sentence end, do not expand
        assert expand_abbreviations("Das kostet ca. Die Kosten", self.ABBR) == "Das kostet ca. Die Kosten"

    def test_sentence_final_skipped_newline_follows(self):
        assert expand_abbreviations("kostet ca.\n\nDie Kosten", self.ABBR) == "kostet ca.\n\nDie Kosten"

    def test_mid_sentence_expanded(self):
        assert expand_abbreviations("kostet ca. 25 Euro", self.ABBR) == "kostet circa 25 Euro"

    def test_no_match_inside_word(self):
        # "s." should not match at end of "des." (word char before s)
        assert expand_abbreviations("des.", self.ABBR) == "des."

    def test_empty_abbr_map(self):
        assert expand_abbreviations("Abb. 3", {}) == "Abb. 3"


class TestNormalizeTextIntegration:
    def test_nbsp_replaced(self):
        result = normalize_text("Hallo\u00a0Welt")  # non-breaking space
        assert result == "Hallo Welt"

    # --- abbreviation expansion is opt-in ---

    def test_abbreviations_not_expanded_by_default(self):
        result = normalize_text("z. B. ein Beispiel")
        assert "z. B." in result

    def test_abbreviations_expanded_when_flag_set(self):
        result = normalize_text("z. B. ein Beispiel", expand_abbr=True)
        assert "zum Beispiel" in result

    # --- section-number expansion is opt-in ---

    def test_section_numbers_not_expanded_by_default(self):
        result = normalize_text("1.1 zeigt die Ergebnisse")
        assert "1.1" in result

    def test_section_numbers_expanded_when_flag_set(self):
        result = normalize_text("Abschn. 1.1 für Details.", expand_numbers=True)
        assert "eins punkt eins" in result

    def test_both_flags_together(self):
        result = normalize_text("s. 1.1 zeigt", expand_abbr=True, expand_numbers=True)
        assert "siehe" in result
        assert "eins punkt eins" in result


class TestCLIOutputFlag:
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "preprocess_text.py", *args],
            capture_output=True, text=True,
        )

    def test_output_writes_to_file(self, tmp_path):
        out = tmp_path / "result.txt"
        self._run("Hallo\u00a0Welt", "-o", str(out))
        assert out.read_text(encoding="utf-8").strip() == "Hallo Welt"

    def test_output_long_flag(self, tmp_path):
        out = tmp_path / "result.txt"
        self._run("Hallo\u00a0Welt", "--output", str(out))
        assert out.read_text(encoding="utf-8").strip() == "Hallo Welt"

    def test_input_short_flag(self, tmp_path):
        src = tmp_path / "in.txt"
        src.write_text("Hallo\u00a0Welt", encoding="utf-8")
        result = self._run("-i", str(src))
        assert result.stdout.strip() == "Hallo Welt"
