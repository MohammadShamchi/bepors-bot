"""Tests for i18n helper."""
from i18n import detect_lang, reload_locales, t, to_fa_digits, SUPPORTED_LANGS


def setup_function(_):
    reload_locales()


def test_fa_digit_conversion():
    assert to_fa_digits("20") == "۲۰"
    assert to_fa_digits("Hello 123") == "Hello ۱۲۳"
    assert to_fa_digits("") == ""


def test_t_interpolates_int_as_persian_for_fa():
    msg = t("welcome", "fa", limit=20)
    assert "۲۰" in msg
    assert "20" not in msg


def test_t_interpolates_int_as_latin_for_en():
    msg = t("welcome", "en", limit=20)
    assert "20" in msg
    assert "۲۰" not in msg


def test_t_falls_back_to_other_lang_when_key_missing():
    # Both locales share the same keys, so force a synthetic miss by using an
    # unknown lang which defaults to fa.
    msg = t("welcome", "xx", limit=20)
    assert "بپرسم" in msg or "Bepors" in msg  # got something, not the key


def test_t_returns_key_on_total_miss():
    assert t("__definitely_missing__", "fa") == "__definitely_missing__"


def test_detect_lang_always_returns_farsi():
    """
    Bepors's audience is Persian-speaking, so detect_lang ignores Telegram's
    language_code and always returns 'fa'. English speakers must opt in
    via /lang en, which persists in users.lang.
    """
    assert detect_lang("fa") == "fa"
    assert detect_lang("fa-IR") == "fa"
    assert detect_lang("en") == "fa"      # was 'en' before; now Farsi default
    assert detect_lang("en-US") == "fa"
    assert detect_lang(None) == "fa"
    assert detect_lang("de") == "fa"


def test_burst_and_quota_strings_have_placeholders():
    for lang in SUPPORTED_LANGS:
        assert "{seconds}" not in t("burst_exceeded", lang, seconds=30)
        assert "{hours}" not in t("quota_exceeded", lang, hours=5)
        # Values should actually appear in the output
        if lang == "fa":
            assert "۳۰" in t("burst_exceeded", lang, seconds=30)
            assert "۵" in t("quota_exceeded", lang, hours=5)
        else:
            assert "30" in t("burst_exceeded", lang, seconds=30)
            assert "5" in t("quota_exceeded", lang, hours=5)


def test_bool_kwargs_not_digit_converted():
    """Ensure bool values don't get converted to Persian '۰/۱'."""
    # Use a key with a placeholder that could accept bool — admin_blocked
    msg = t("admin_blocked", "fa", user_id=True)
    assert "True" in msg  # bools are not converted
