from dashboard.i18n import LANGUAGES, STRINGS, VALUE_LABELS, label, t


def test_every_string_has_every_language():
    for key, texts in STRINGS.items():
        assert set(texts) == set(LANGUAGES), key


def test_every_value_label_has_every_language():
    for value, texts in VALUE_LABELS.items():
        assert set(texts) == set(LANGUAGES), value


def test_placeholders_match_across_languages():
    import string

    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
    for key, texts in STRINGS.items():
        assert fields(texts["zh"]) == fields(texts["en"]), key


def test_t_formats_and_label_falls_back():
    assert t("m_days", "en", n=3) == "3 trading days"
    assert label("单次建仓", "en") == "Single entry"
    assert label("0DTE", "en") == "0DTE"
