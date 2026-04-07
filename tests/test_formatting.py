"""Tests for formatting module: renderers, escape, split, kv enhance."""
from formatting import (
    enhance_kv_lines,
    escape_markdown_v2,
    normalize_sources,
    parse_mode_for,
    render,
    split_long,
)


# ---- escape ----------------------------------------------------------------

def test_escape_markdown_v2_reserved():
    out = escape_markdown_v2("hello *world* [x](y)!")
    assert "\\*" in out
    assert "\\[" in out
    assert "\\!" in out


def test_escape_markdown_v2_empty():
    assert escape_markdown_v2("") == ""


# ---- parse_mode_for --------------------------------------------------------

def test_parse_mode_for_compact_is_html():
    assert parse_mode_for("compact") == "HTML"


def test_parse_mode_for_detailed_is_html():
    assert parse_mode_for("detailed") == "HTML"


def test_parse_mode_for_markdown():
    assert parse_mode_for("markdown") == "MarkdownV2"


# ---- enhance_kv_lines ------------------------------------------------------

def test_enhance_kv_lines_adds_emoji_and_fa_digits():
    out = enhance_kv_lines("خرید: 82,300 تومان\nفروش: 82,800 تومان", "fa")
    assert "💰" in out
    assert "۸۲" in out
    assert "82" not in out


def test_enhance_kv_lines_leaves_prose_alone():
    text = "The weather in Tehran is sunny and warm today."
    assert enhance_kv_lines(text, "en") == text


def test_enhance_kv_lines_idempotent():
    text = "Price: 100 USD"
    once = enhance_kv_lines(text, "en")
    twice = enhance_kv_lines(once, "en")
    assert once == twice


def test_enhance_kv_lines_skips_lines_without_digits():
    text = "Name: John\nAge: 30"
    out = enhance_kv_lines(text, "en")
    assert "Name: John" in out  # no digit → unchanged
    assert "30" in out
    # Age line should have an emoji prepended
    age_line = [ln for ln in out.split("\n") if "Age" in ln][0]
    assert any(ord(c) > 0x2600 for c in age_line)


# ---- normalize_sources -----------------------------------------------------

def test_normalize_sources_dedupes_by_domain():
    raw = [
        {"title": "A", "url": "https://bbc.com/a"},
        {"title": "B", "url": "https://bbc.com/b"},
        {"title": "C", "url": "https://cnn.com/1"},
    ]
    out = normalize_sources(raw)
    assert len(out) == 2
    assert out[0].url == "https://bbc.com/a"
    assert out[1].url == "https://cnn.com/1"


def test_normalize_sources_caps_at_max():
    raw = [{"title": f"T{i}", "url": f"https://d{i}.com/"} for i in range(10)]
    assert len(normalize_sources(raw, max_sources=5)) == 5


def test_normalize_sources_empty():
    assert normalize_sources(None) == []
    assert normalize_sources([]) == []


# ---- render (compact HTML) -------------------------------------------------

def test_render_compact_escapes_html_in_answer():
    chunks = render(
        "answer with <tag> & ampersand",
        None,
        format="compact",
        lang="en",
        search_used=True,
        remaining=15,
    )
    # The answer body must be HTML-escaped
    assert "&lt;tag&gt;" in chunks[0]
    assert "&amp;" in chunks[0]


def test_render_compact_includes_tappable_sources():
    chunks = render(
        "answer",
        [{"title": "BBC News", "url": "https://bbc.com/news/x"}],
        format="compact",
        lang="en",
        search_used=True,
        remaining=15,
    )
    # Single <a> tag with the URL, domain shown as the link text
    assert '<a href="https://bbc.com/news/x">' in chunks[0]
    assert "[1] bbc.com" in chunks[0]


def test_render_compact_no_footer_when_search_on_and_plenty_remaining():
    chunks = render(
        "hello",
        None,
        format="compact",
        lang="en",
        search_used=True,
        remaining=15,
    )
    assert len(chunks) == 1
    assert "left today" not in chunks[0]
    assert "live search" not in chunks[0]


def test_render_compact_shows_warning_when_search_off():
    chunks = render(
        "hello",
        None,
        format="compact",
        lang="en",
        search_used=False,
        remaining=15,
        show_warning=True,
    )
    assert "OFF" in chunks[0] or "Off" in chunks[0] or "off" in chunks[0]


def test_render_compact_shows_remaining_when_low():
    chunks = render(
        "hi", None, format="compact", lang="en", search_used=True, remaining=3
    )
    assert "3" in chunks[0]
    assert "left today" in chunks[0]


def test_render_detailed_has_bold_headers():
    chunks = render(
        "First para.\n\nSecond para.",
        [{"title": "T", "url": "https://x.com/"}],
        format="detailed",
        lang="en",
        search_used=True,
        remaining=15,
    )
    assert "<b>Summary</b>" in chunks[0]
    assert "<b>Details</b>" in chunks[0]
    # Sources label is bolded as "<b>Sources:</b>" in the one-line footer
    assert "<b>Sources:</b>" in chunks[0]


# ---- render (markdown) -----------------------------------------------------

def test_render_markdown_escapes_reserved_chars():
    chunks = render(
        "answer with * and _ and [ and ]!",
        None,
        format="markdown",
        lang="en",
        search_used=True,
        remaining=15,
    )
    assert "\\*" in chunks[0]
    assert "\\_" in chunks[0]
    assert "\\[" in chunks[0]
    assert "\\!" in chunks[0]


# ---- split_long ------------------------------------------------------------

def test_split_long_single_chunk_untouched():
    out = split_long("short", 100, "en")
    assert out == ["short"]


def test_split_long_paginates_with_indicators():
    # Build many paragraphs so total > max_len
    paragraphs = ["Paragraph " + "x" * 100] * 10
    text = "\n\n".join(paragraphs)
    out = split_long(text, 500, "en")
    assert len(out) > 1
    # First chunk is tagged (1/N)
    assert out[0].startswith("(1/")


def test_split_long_fa_uses_persian_digits():
    text = "\n\n".join(["chunk " + "y" * 200] * 5)
    out = split_long(text, 300, "fa")
    if len(out) > 1:
        assert "۱" in out[0]  # Persian digit in page indicator
