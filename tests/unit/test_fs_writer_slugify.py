"""Slugify must preserve non-Latin scripts and survive empty / weird inputs."""

from __future__ import annotations

from gampan.core.fs.writer import slugify


def test_ascii_lowercased_and_dashed() -> None:
    assert slugify("Standard Text Ad") == "standard-text-ad"


def test_underscores_and_dashes_preserved() -> None:
    assert slugify("mobile_v2 - foo") == "mobile_v2-foo"


def test_hangul_passes_through() -> None:
    # Korean letters are Unicode category Lo (letter-other); kept verbatim.
    assert slugify("한국어 네이티브 광고") == "한국어-네이티브-광고"


def test_kanji_and_kana_passes_through() -> None:
    assert slugify("看板  かんばん  バナー") == "看板-かんばん-バナー"


def test_cyrillic_passes_through() -> None:
    assert slugify("Привет Мир") == "привет-мир"


def test_accented_latin_lowercased_in_place() -> None:
    assert slugify("Café résumé") == "café-résumé"


def test_emoji_stripped() -> None:
    # Emoji are Unicode category So (symbol-other); not alnum → replaced.
    assert slugify("🚀 launch! 🎉") == "launch"


def test_path_separators_replaced() -> None:
    # Critical: no filesystem-traversal-shaped output is allowed.
    assert "/" not in slugify("a/b/c")
    assert "\\" not in slugify("a\\b\\c")


def test_all_punctuation_yields_empty() -> None:
    assert slugify("!!!@@@###") == ""


def test_korean_only_yields_korean_slug_not_empty() -> None:
    # Regression: NativeStyles whose name was Korean-only previously
    # slugified to "" because [^a-z0-9_-] stripped them.
    assert slugify("한국어광고") == "한국어광고"
    assert slugify("한국어광고") != ""


def test_nfc_normalisation() -> None:
    # NFD and NFC representations of the same string must produce the same slug.
    nfd = "개"  # ㄱ + ㅐ in jamo form
    nfc = "개"  # 개 (single precomposed syllable)
    assert slugify(nfd) == slugify(nfc) == "개"


def test_length_cap() -> None:
    long_name = "a" * 200
    assert len(slugify(long_name)) == 80


def test_leading_trailing_dashes_stripped() -> None:
    assert slugify("---foo---") == "foo"
    assert slugify("   foo   ") == "foo"
