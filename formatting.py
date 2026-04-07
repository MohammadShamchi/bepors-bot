"""
Reply formatters for Bepors: compact, detailed, markdown.
Per PRD §5.4.

Public API:
    render(answer, sources, *, format, lang, search_used, remaining) -> list[str]

Returns one or more Telegram-sized chunks. Each chunk is at most MAX_CHUNK chars
and is split on paragraph boundaries, never mid-sentence, with (۱/۳)-style page
indicators for multi-chunk replies.

Parse modes per format:
- compact  / detailed → HTML  (sources rendered as inline <a href> tags)
- markdown            → MarkdownV2

Callers must use `parse_mode_for(format)` to pick the matching parse_mode
when sending each chunk.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal

from i18n import t, to_fa_digits

MAX_CHUNK = 3800  # keep a margin under Telegram's 4096-char hard limit
Format = Literal["compact", "detailed", "markdown"]


def parse_mode_for(format: Format) -> str | None:
    """Return the Telegram parse_mode string corresponding to a format."""
    if format == "markdown":
        return "MarkdownV2"
    if format in ("compact", "detailed"):
        return "HTML"
    return None

# MarkdownV2 reserved characters per Telegram Bot API docs.
_MDV2_RESERVED = r"_*[]()~`>#+-=|{}.!\\"
_MDV2_ESCAPE_RE = re.compile(f"([{re.escape(_MDV2_RESERVED)}])")


def escape_markdown_v2(text: str) -> str:
    """Escape every MarkdownV2 reserved char. Safe to apply to raw model output."""
    if not text:
        return ""
    return _MDV2_ESCAPE_RE.sub(r"\\\1", text)


# ---- source normalization ---------------------------------------------------

@dataclass(frozen=True)
class Source:
    title: str
    url: str


def normalize_sources(raw: list[dict] | None, max_sources: int = 5) -> list[Source]:
    """Dedupe by domain, cap at max_sources."""
    if not raw:
        return []
    seen_domains: set[str] = set()
    out: list[Source] = []
    for item in raw:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip() or url
        if not url:
            continue
        domain = _domain_of(url)
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        out.append(Source(title=title, url=url))
        if len(out) >= max_sources:
            break
    return out


def _domain_of(url: str) -> str:
    m = re.search(r"https?://([^/]+)/?", url)
    return (m.group(1) if m else url).lower()


# ---- numeric card builder ---------------------------------------------------
#
# We deliberately DO NOT use ASCII box-drawing characters because Telegram renders
# messages in a proportional font by default — box edges would render misaligned.
# Instead we emit simple emoji-led key:value lines that look clean in any font.

# Match "label: number [unit]" lines, e.g. "خرید: ۸۲٬۳۰۰ تومان" or "Buy: 82,300 Toman"
_KV_RE = re.compile(
    r"^\s*(?P<label>[^\n:：]{1,30})\s*[:：]\s*(?P<value>[^\n]{1,60})\s*$",
    re.MULTILINE,
)

# Heuristic emoji pick by label or value keywords. Falls back to ▫️.
_EMOJI_HINTS = (
    (re.compile(r"(price|rate|buy|sell|usd|irr|cost|قیمت|خرید|فروش|تومان|ریال|دلار|یورو)", re.I), "💰"),
    (re.compile(r"(change|diff|تغییر|درصد|%)", re.I), "📈"),
    (re.compile(r"(weather|temp|humid|wind|هوا|دما|رطوبت|باد)", re.I), "🌤"),
    (re.compile(r"(score|match|goal|امتیاز|گل|بازی)", re.I), "🏆"),
    (re.compile(r"(stock|market|shares|سهام|بازار)", re.I), "📊"),
)


def _pick_emoji(label: str, value: str) -> str:
    hay = f"{label} {value}"
    for pat, emoji in _EMOJI_HINTS:
        if pat.search(hay):
            return emoji
    return "▫️"


def enhance_kv_lines(answer: str, lang: str) -> str:
    """
    Walk the answer line-by-line. For every "label: value" line where the
    value contains a digit, prepend a context-appropriate emoji so the key
    data stands out at a glance. Leaves prose lines untouched.

    This is the replacement for the old ASCII-box "card" — instead of
    duplicating the KV block above the answer, we decorate the KV lines
    in place. Font-safe, no parse_mode required.

    Also converts ASCII digits to Persian digits on enhanced lines when
    lang == "fa".
    """
    if not answer:
        return answer

    def _enhance_line(line: str) -> str:
        m = re.match(r"^(\s*)(?P<label>[^\n:：]{1,30})\s*([:：])\s*(?P<value>.+?)\s*$", line)
        if not m:
            return line
        label, value = m.group("label"), m.group("value")
        # Must contain a digit (ASCII or Persian) — otherwise it's conversational
        if not re.search(r"[\d۰-۹]", value):
            return line
        # Skip lines that already start with an emoji / bullet
        leading = line.lstrip()[:2]
        if leading and any(ord(c) > 0x2600 for c in leading):
            return line
        emoji = _pick_emoji(label, value)
        if lang == "fa":
            label = to_fa_digits(label)
            value = to_fa_digits(value)
        sep = m.group(3)
        return f"{m.group(1)}{emoji} {label.strip()}{sep} {value}"

    return "\n".join(_enhance_line(ln) for ln in answer.splitlines())


# Keep the old name for backward compat with any external references, but
# mark it as the enhancer.
try_build_card = enhance_kv_lines


# ---- main render entry point -----------------------------------------------

#: Show the "X questions left today" footer only when remaining is at or below
#: this threshold. Default state = no footer chrome = less nagging.
REMAINING_FOOTER_THRESHOLD = 5


def render(
    answer: str,
    sources: list[dict] | None,
    *,
    format: Format,
    lang: str,
    search_used: bool,
    remaining: int,
    show_warning: bool = False,
) -> list[str]:
    answer = (answer or "").strip()
    srcs = normalize_sources(sources)

    # Enhance "label: value" lines with leading emoji + Persian digits.
    # Done as an in-place transformation of the answer text, before format
    # dispatch, so every renderer (compact/detailed/markdown) benefits.
    # Skipped for markdown because MarkdownV2 escaping runs later.
    if format != "markdown":
        answer = enhance_kv_lines(answer, lang)

    if format == "detailed":
        body = _render_detailed(answer, srcs, lang)
    elif format == "markdown":
        body = _render_markdown(answer, srcs, lang)
    else:
        body = _render_compact(answer, srcs, lang)

    # Footer logic: minimize chrome.
    #  - Live search ON  + plenty of quota  → no footer at all
    #  - Live search OFF                    → show warning (user needs to know)
    #  - Remaining ≤ threshold              → show remaining count
    footer_parts: list[str] = []
    if not search_used:
        footer_parts.append(
            t("search_off_warning" if show_warning else "search_off_footer", lang)
        )
    if remaining <= REMAINING_FOOTER_THRESHOLD:
        footer_parts.append(t("remaining_footer", lang, remaining=remaining))

    if footer_parts:
        footer_text = "\n".join(footer_parts)
        # Escape the footer to match the parse_mode of the body.
        if format in ("compact", "detailed"):
            footer_text = _esc(footer_text)
        elif format == "markdown":
            footer_text = escape_markdown_v2(footer_text)
        body = body + "\n\n" + footer_text

    return split_long(body, MAX_CHUNK, lang, markdown=(format == "markdown"))


# ---- renderers --------------------------------------------------------------

def _html_sources_footer(sources: list[Source], lang: str) -> str:
    """
    One-line tappable source list for compact/detailed HTML renders.
    Format: "🔗 <b>Sources:</b> <a>[1] bbc</a> · <a>[2] tgju</a>"
    """
    if not sources:
        return ""
    label = t("sources_label", lang).replace("🔗", "").replace(":", "").strip()
    pieces: list[str] = []
    for i, s in enumerate(sources, 1):
        domain = _domain_of(s.url)
        if domain.startswith("www."):
            domain = domain[4:]
        idx = _num(i, lang)
        # URL goes inside an HTML attribute, so full escaping (quote=True) is required.
        url_attr = html.escape(s.url, quote=True)
        pieces.append(f'<a href="{url_attr}">[{idx}] {_esc(domain)}</a>')
    return f"🔗 <b>{_esc(label)}:</b> " + " · ".join(pieces)


def _esc(s: str) -> str:
    """HTML-escape body text. quote=False keeps apostrophes readable in output."""
    return html.escape(s or "", quote=False)


def _render_compact(answer: str, sources: list[Source], lang: str) -> str:
    """HTML-escaped answer body + one-line tappable source footer."""
    parts = [_esc(answer)]
    footer = _html_sources_footer(sources, lang)
    if footer:
        parts.append("")
        parts.append(footer)
    return "\n".join(parts)


def _render_detailed(answer: str, sources: list[Source], lang: str) -> str:
    """HTML with <b> section headers and a tappable source footer."""
    summary, rest = _split_summary(answer)
    out = [f"📌 <b>{_esc(t('detailed_summary', lang))}</b>", _esc(summary)]
    if rest:
        out.append("")
        out.append(f"📖 <b>{_esc(t('detailed_details', lang))}</b>")
        out.append(_esc(rest))
    footer = _html_sources_footer(sources, lang)
    if footer:
        out.append("")
        out.append(footer)
    return "\n".join(out)


def _render_markdown(answer: str, sources: list[Source], lang: str) -> str:
    # Every piece of model text must be escaped before interpolation.
    esc_answer = escape_markdown_v2(answer)
    out = [f"*{escape_markdown_v2(t('detailed_summary', lang))}*", esc_answer]
    if sources:
        out.append("")
        out.append(f"*{escape_markdown_v2(t('detailed_sources', lang))}*")
        for i, s in enumerate(sources, 1):
            title = escape_markdown_v2(s.title)
            # URLs inside MarkdownV2 link must escape ) and \
            url_escaped = s.url.replace("\\", "\\\\").replace(")", "\\)")
            out.append(f"{i}\\. [{title}]({url_escaped})")
    return "\n".join(out)


def _split_summary(text: str) -> tuple[str, str]:
    """First paragraph is the summary, the rest is details."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text, ""
    if len(paragraphs) == 1:
        # Fall back to first sentence
        first = re.split(r"(?<=[.!؟?])\s+", paragraphs[0], maxsplit=1)
        if len(first) == 2 and len(first[0]) < len(paragraphs[0]) - 20:
            return first[0], first[1]
        return paragraphs[0], ""
    return paragraphs[0], "\n\n".join(paragraphs[1:])


# ---- long-message splitter --------------------------------------------------

def split_long(text: str, max_len: int, lang: str, *, markdown: bool = False) -> list[str]:
    """
    Split text on paragraph boundaries so no chunk exceeds max_len.
    Adds (i/n) page indicators to every chunk if more than one.
    """
    if len(text) <= max_len:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        candidate = f"{buf}\n\n{p}" if buf else p
        if len(candidate) <= max_len:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        # A single paragraph bigger than max_len → hard-split on sentence/char
        if len(p) > max_len:
            for sub in _hard_split(p, max_len):
                if len(sub) > max_len:
                    # Last resort: raw slice
                    for i in range(0, len(sub), max_len):
                        chunks.append(sub[i : i + max_len])
                else:
                    chunks.append(sub)
        else:
            buf = p
    if buf:
        chunks.append(buf)

    total = len(chunks)
    if total <= 1:
        return chunks
    out: list[str] = []
    for i, c in enumerate(chunks, 1):
        idx = f"({_num(i, lang)}/{_num(total, lang)})"
        out.append(f"{idx}\n{c}" if not markdown else f"{escape_markdown_v2(idx)}\n{c}")
    return out


def _hard_split(text: str, max_len: int) -> list[str]:
    """Split a single oversized paragraph at sentence boundaries."""
    sentences = re.split(r"(?<=[.!؟?])\s+", text)
    out: list[str] = []
    buf = ""
    for s in sentences:
        candidate = f"{buf} {s}".strip() if buf else s
        if len(candidate) <= max_len:
            buf = candidate
        else:
            if buf:
                out.append(buf)
            buf = s
    if buf:
        out.append(buf)
    return out


def _num(n: int, lang: str) -> str:
    return to_fa_digits(str(n)) if lang == "fa" else str(n)
