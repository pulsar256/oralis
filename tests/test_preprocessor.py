from web.preprocessor import apply_steps, diff_html, preview, full_diff, default_steps, KNOWN_STEPS

def test_known_steps_have_id_and_label():
    assert len(KNOWN_STEPS) == 4
    for step in KNOWN_STEPS:
        assert "id" in step
        assert "label" in step

def test_apply_steps_no_steps_returns_original():
    assert apply_steps("Hallo Welt", []) == "Hallo Welt"

def test_apply_steps_expand_abbreviations():
    text = "Dies ist z. B. ein Test."
    result = apply_steps(text, [
        {"id": "expand_abbreviations", "enabled": True},
    ])
    assert "zum Beispiel" in result

def test_diff_html_marks_changes():
    html = diff_html("Abb. zeigt", "Abbildung zeigt")
    assert "<del>" in html
    assert "<ins>" in html

def test_diff_html_no_change():
    html = diff_html("same text", "same text")
    assert "<del>" not in html
    assert "same text" in html

def test_diff_html_empty_original():
    html = diff_html("", "hello world")
    assert "<ins>" in html
    assert "<del>" not in html

def test_diff_html_empty_both():
    assert diff_html("", "") == ""

def test_preview_returns_html_string():
    result = preview("Hallo Welt", [{"id": "expand_abbreviations", "enabled": True}])
    assert isinstance(result, str)

def test_full_diff_returns_html_string():
    result = full_diff("Dies ist z. B. ein Test.", [
        {"id": "expand_abbreviations", "enabled": True},
    ])
    assert "Beispiel" in result

def test_default_steps():
    steps = default_steps()
    assert len(steps) == len(KNOWN_STEPS)
    assert [s["id"] for s in steps] == [s["id"] for s in KNOWN_STEPS]
    by_id = {s["id"]: s for s in steps}
    assert by_id["normalize_unicode"]["enabled"] is True
    assert by_id["expand_abbreviations"]["enabled"] is False
    assert by_id["expand_section_numbers"]["enabled"] is False
