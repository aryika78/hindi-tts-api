"""Tests for the IPA→Devanagari converter (pure Python, no espeak-ng needed)."""

from src.tts.normalizer import _ipa_to_devanagari, _tokenize_ipa


# --- Tokenizer ---

def test_tokenize_strips_stress():
    tokens = _tokenize_ipa("məˈʃiːn")
    assert "ˈ" not in tokens


def test_tokenize_diphthong():
    tokens = _tokenize_ipa("aɪ")
    assert tokens == ["aɪ"]  # single diphthong token, not ['a', 'ɪ']


def test_tokenize_affricate():
    tokens = _tokenize_ipa("tʃ")
    assert tokens == ["tʃ"]  # single affricate, not ['t', 'ʃ']


def test_tokenize_long_vowel():
    tokens = _tokenize_ipa("iː")
    assert tokens == ["iː"]


# --- IPA → Devanagari: individual phoneme tests ---

def test_machine():
    # məˈʃiːn → मश��न
    result = _ipa_to_devanagari("məˈʃiːn")
    assert result == "मशीन"


def test_learning():
    # lˈɜːnɪŋ → लर्निंग
    result = _ipa_to_devanagari("lˈɜːnɪŋ")
    assert result == "लर्निंग"


def test_server():
    # sˈɜːvɚ → सर्वर
    result = _ipa_to_devanagari("sˈɜːvɚ")
    assert result == "सर्वर"


def test_streaming():
    # stɹˈiːmɪŋ → स्ट्रीमिंग
    result = _ipa_to_devanagari("stɹˈiːmɪŋ")
    assert result == "स्ट्रीमिंग"


def test_meeting():
    # mˈiːɾɪŋ → मीटिंग (ɾ = flapped t, not r)
    result = _ipa_to_devanagari("mˈiːɾɪŋ")
    assert result == "मीटिंग"


def test_computer():
    # kəmpjˈuːɾɚ → कम्प्यूटर
    result = _ipa_to_devanagari("kəmpjˈuːɾɚ")
    assert result == "कम्प्यूटर"


def test_water():
    # wˈɔːɾɚ → वॉटर
    result = _ipa_to_devanagari("wˈɔːɾɚ")
    assert result == "वॉटर"


def test_city():
    # sˈɪɾi → सिटी (word-final i → long ī)
    result = _ipa_to_devanagari("sˈɪɾi")
    assert result == "सिटी"


def test_software():
    # sˈɔftwɛɹ → includes ɔ (short open-o) which must not be dropped
    result = _ipa_to_devanagari("sˈɔftwɛɹ")
    assert "ॉ" in result or "ऑ" in result  # ɔ must appear as ऑ/ॉ


def test_ng_before_vowel():
    # æŋɡɹi (angry) → ŋ before ɡ should not double the ग
    result = _ipa_to_devanagari("ˈæŋɡɹi")
    assert "गग" not in result  # no double ग
    assert "ंग" in result       # anusvara + ga present


# --- Edge cases ---

def test_empty_string():
    assert _ipa_to_devanagari("") == ""


def test_only_stress_markers():
    assert _ipa_to_devanagari("ˈˌ") == ""


def test_consonant_cluster_with_halant():
    # st → स्ट (joined with halant)
    result = _ipa_to_devanagari("stɪŋ")
    assert "स्ट" in result
