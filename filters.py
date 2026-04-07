"""
Inline flag parser, content safety filter, and badwords censor.
Per PRD §5.3 (filters) and §5.5 (content safety + swear censor).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Supported inline flags. Keep in sync with the help string in locales/*.json.
_FLAG_RE = re.compile(
    r"--(?P<key>site|lang|time|region|news|academic)(?::(?P<val>[^\s]+))?",
    re.IGNORECASE,
)

_VALID_TIME = {"day", "week", "month", "year"}
_VALID_LANG = {"fa", "en", "ar"}
# Region: ISO-ish 2-letter code, not exhaustive
_REGION_RE = re.compile(r"^[a-z]{2}$", re.IGNORECASE)

# ---- prefix shortcut --------------------------------------------------------

def detect_prefix(text: str) -> tuple[str, Optional[bool]]:
    """
    Per §5.2.4:
    - '?' at start → force search ON for this query (strip prefix)
    - '.' at start → force search OFF for this query (strip prefix)
    - Returns (cleaned_text, force_search). force_search is None if no prefix.
    """
    if not text:
        return text, None
    stripped = text.lstrip()
    if stripped.startswith("?"):
        return stripped[1:].lstrip(), True
    if stripped.startswith("."):
        return stripped[1:].lstrip(), False
    return text, None


# ---- inline flag parser -----------------------------------------------------

def parse_flags(text: str) -> tuple[str, dict[str, str]]:
    """
    Extract --key:value flags from the message. Returns (cleaned_text, flags).
    Unknown or invalid-value flags are silently dropped.
    """
    flags: dict[str, str] = {}
    cleaned_parts: list[str] = []
    last = 0
    for m in _FLAG_RE.finditer(text):
        cleaned_parts.append(text[last : m.start()])
        last = m.end()
        key = m.group("key").lower()
        val = (m.group("val") or "").strip()
        if key in ("news", "academic"):
            # boolean flags
            flags[key] = "true"
            if key == "news":
                flags.setdefault("time", "day")
            continue
        if not val:
            continue
        if key == "time" and val.lower() in _VALID_TIME:
            flags["time"] = val.lower()
        elif key == "lang" and val.lower() in _VALID_LANG:
            flags["lang"] = val.lower()
        elif key == "region" and _REGION_RE.match(val):
            flags["region"] = val.lower()
        elif key == "site":
            # Basic sanity: drop whitespace and protocol
            v = val.replace("https://", "").replace("http://", "").strip("/ ")
            if v and "." in v:
                flags["site"] = v
    cleaned_parts.append(text[last:])
    cleaned = re.sub(r"\s+", " ", "".join(cleaned_parts)).strip()
    return cleaned, flags


def merge_filters(defaults: dict[str, str], inline: dict[str, str]) -> dict[str, str]:
    """Inline flags take precedence over persisted defaults."""
    merged = dict(defaults or {})
    merged.update(inline or {})
    return merged


def flags_to_constraints(flags: dict[str, str], lang: str) -> str:
    """
    Convert filter flags into a natural-language constraint block for the Gemini
    system instruction. Per §5.3.2, the model is told to prefer matching sources.
    """
    if not flags:
        return ""
    lines: list[str] = []
    if "site" in flags:
        lines.append(f"- Prefer sources from the domain {flags['site']} (strongly).")
    if "time" in flags:
        freshness = {
            "day": "published within the last 24 hours",
            "week": "published within the last 7 days",
            "month": "published within the last 30 days",
            "year": "published within the last 12 months",
        }[flags["time"]]
        lines.append(f"- Only use sources {freshness}.")
    if "lang" in flags:
        lines.append(f"- Prefer sources written in '{flags['lang']}'.")
    if "region" in flags:
        lines.append(f"- Prefer sources from region '{flags['region'].upper()}'.")
    if flags.get("news") == "true":
        lines.append("- Focus on current news reporting; cite reputable news outlets.")
    if flags.get("academic") == "true":
        lines.append("- Prefer scholarly / academic / peer-reviewed sources where possible.")
    header = "User-requested constraints (obey strictly, skip non-matching sources):"
    return header + "\n" + "\n".join(lines)


# ---- jailbreak / prompt-injection pre-filter --------------------------------

_JAILBREAK_PATTERNS = [
    r"ignore (all |the |your |previous |above )*(instructions|prompt|rules)",
    r"system\s+prompt",
    r"reveal\s+(your|the)\s+(system|hidden|initial)\s*prompt",
    r"disregard\s+(all|previous|prior)",
    r"developer\s+mode",
    r"jailbreak",
    r"DAN\s+mode",
    r"act as .* (with no|without) (any )?(restriction|filter|rule)",
]
_JAILBREAK_RE = re.compile("|".join(_JAILBREAK_PATTERNS), re.IGNORECASE)


def is_jailbreak(text: str) -> bool:
    """Cheap pre-filter. Not a security boundary, just a deterrent."""
    if not text:
        return False
    return bool(_JAILBREAK_RE.search(text))


# ---- unsafe output post-filter ----------------------------------------------

_UNSAFE_OUTPUT_PATTERNS = [
    # Weapon synthesis / detailed instructions
    r"\bhow to (make|build|synthesize|produce) (a )?(bomb|explosive|nerve agent|sarin|anthrax)\b",
    # Self-harm enablement
    r"\b(how to|best way to) (kill|hang|cut|poison) (myself|yourself)\b",
    # CSAM
    r"\b(child|minor|underage).{0,20}(porn|sexual|nude|erotic)\b",
]
_UNSAFE_OUTPUT_RE = re.compile("|".join(_UNSAFE_OUTPUT_PATTERNS), re.IGNORECASE)


def is_unsafe_output(text: str) -> bool:
    if not text:
        return False
    return bool(_UNSAFE_OUTPUT_RE.search(text))


# ---- badwords censor --------------------------------------------------------

_BADWORDS_CACHE: dict[str, list[str]] = {}


def _load_badwords(lang: str) -> list[str]:
    if lang in _BADWORDS_CACHE:
        return _BADWORDS_CACHE[lang]
    path = Path(__file__).parent / "locales" / f"badwords_{lang}.txt"
    words: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                words.append(line)
    _BADWORDS_CACHE[lang] = words
    return words


def censor_badwords(text: str, lang: str = "fa") -> str:
    """Replace known swears with ***. Run on outgoing text only."""
    if not text:
        return text
    out = text
    for lg in (lang, "en" if lang != "en" else "fa"):
        for word in _load_badwords(lg):
            if not word:
                continue
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            out = pattern.sub("*" * len(word), out)
    return out
