"""
i18n helper: loads locale JSON files once and exposes t(key, lang, **kwargs).
Per PRD §5.1. Farsi is primary, English is secondary.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("bepors.i18n")

SUPPORTED_LANGS = ("fa", "en")
DEFAULT_LANG = "fa"

# Telegram language_code values that should map to Farsi by default.
# Everything else (including missing) falls back to English unless user overrides.
_FA_CODES = {"fa", "fa-ir", "fas", "prs"}

_LOCALES_DIR = Path(__file__).parent / "locales"
_cache: dict[str, dict[str, str]] = {}

# Digit conversion for Persian locale.
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"
_FA_DIGIT_TABLE = str.maketrans(_EN_DIGITS, _FA_DIGITS)


def to_fa_digits(s: str) -> str:
    """Convert ASCII digits to Persian digits. Identity on non-digit chars."""
    return s.translate(_FA_DIGIT_TABLE)


def _load(lang: str) -> dict[str, str]:
    if lang in _cache:
        return _cache[lang]
    path = _LOCALES_DIR / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.error("locale file missing: %s", path)
        data = {}
    except json.JSONDecodeError as e:
        log.error("locale %s invalid json: %s", lang, e)
        data = {}
    _cache[lang] = data
    return data


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    """
    Return localized string for `key` in `lang`, interpolating {var} placeholders.
    Falls back to the other language, then to the key itself, so the bot never crashes.

    When lang == 'fa', int/float kwargs are auto-converted to Persian digits so
    strings like "روزانه {limit} سوال" render as "روزانه ۲۰ سوال" instead of "20".
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    data = _load(lang)
    template = data.get(key)
    if template is None:
        # try the other language as fallback
        other = "en" if lang == "fa" else "fa"
        template = _load(other).get(key, key)
    if not kwargs:
        return template
    if lang == "fa":
        kwargs = {
            k: (to_fa_digits(str(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
            for k, v in kwargs.items()
        }
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def detect_lang(language_code: str | None) -> str:
    """
    Resolve the *initial* language for a brand-new user.

    Bepors's audience is Persian-speaking, so the bot defaults to Farsi for
    EVERY new user regardless of their Telegram client language. English
    speakers explicitly opt in via `/lang en`. The choice persists in the
    `users.lang` column, so this function only matters on first contact.

    The `language_code` argument is accepted (and ignored) so callers don't
    have to special-case the call site.
    """
    return DEFAULT_LANG


def reload_locales() -> None:
    """Clear the in-memory cache. Useful for tests or hot-reload."""
    _cache.clear()
