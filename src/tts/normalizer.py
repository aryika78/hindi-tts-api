"""Hindi text normalizer for Piper TTS.

Pipeline:
1. Dates (any format) -> dateparser detects -> convert to "D MonthName YYYY" -> Kenpath verbalizes
2. Acronyms (ALL-CAPS) -> spelled-out Hindi letters
3. English words -> espeak-ng IPA -> phonetic Devanagari
4. Everything else (numbers, currency, time, measures) -> Kenpath WFST
"""

import re
import subprocess
from dateparser.search import search_dates
from indic_text_normalization import Normalizer

_normalizer = Normalizer(lang="hi", input_case="cased")

_DP_SETTINGS = {
    "DATE_ORDER": "DMY",
    "STRICT_PARSING": True,
    "RETURN_AS_TIMEZONE_AWARE": False,
}

HINDI_MONTHS = {
    1: "जनवरी", 2: "फरवरी", 3: "मार्च", 4: "अप्रैल",
    5: "मई", 6: "जून", 7: "जुलाई", 8: "अगस्त",
    9: "सितंबर", 10: "अक्टूबर", 11: "नवंबर", 12: "दिसंबर",
}

LETTER_TO_HINDI = {
    "A": "ए", "B": "बी", "C": "सी", "D": "डी", "E": "ई",
    "F": "एफ", "G": "जी", "H": "एच", "I": "आई", "J": "जे",
    "K": "के", "L": "एल", "M": "एम", "N": "एन", "O": "ओ",
    "P": "पी", "Q": "क्यू", "R": "आर", "S": "एस", "T": "टी",
    "U": "यू", "V": "वी", "W": "डब्ल्यू", "X": "एक्स", "Y": "वाई",
    "Z": "ज़ेड",
}

# ---------------------------------------------------------------------------
# IPA → Devanagari phoneme tables
# ---------------------------------------------------------------------------

# Vowels: IPA symbol → (independent Devanagari form, matra after consonant)
# Empty matra string = inherent schwa (no explicit matra written in Devanagari)
_IPA_VOWELS: dict[str, tuple[str, str]] = {
    # Diphthongs — checked before single-char vowels
    "aɪ": ("ऐ",  "ै"),
    "aʊ": ("औ",  "ौ"),
    "eɪ": ("ए",  "े"),
    "oʊ": ("ओ",  "ो"),
    "ɔɪ": ("ओइ", "ोइ"),
    "ɪə": ("इअ", "िअ"),
    "eə": ("एअ", "ेअ"),
    "ʊə": ("उअ", "ुअ"),
    # R-colored vowels — Hindi speakers hear these as consonant र
    "ɜː": ("अर", "र्"),  # "her", "learning" → र् after consonant
    "ɝː": ("अर", "र्"),  # same, American variant
    "ɝ":  ("अर", "र्"),  # same, short
    "ɚ":  ("अर", "र"),   # word-final "server"→सर्वर, "computer"→कम्प्यूटर
    # Long vowels — checked before short vowels
    "iː": ("ई",  "ी"),
    "uː": ("ऊ",  "ू"),
    "ɑː": ("आ",  "ा"),
    "ɔː": ("ऑ",  "ॉ"),
    "aː": ("आ",  "ा"),
    "eː": ("ए",  "े"),
    "oː": ("ओ",  "ो"),
    # Short vowels
    "ə":  ("अ",  ""),   # schwa → inherent vowel, no explicit matra
    "ʌ":  ("अ",  ""),   # same approximation
    "ɐ":  ("अ",  ""),   # near-open central (espeak-ng uses for unstressed ʌ)
    "ᵻ":  ("इ",  "ि"),  # barred i — reduced vowel in unstressed syllables (delivery, quality, city)
    "ɪ":  ("इ",  "ि"),
    "ʊ":  ("उ",  "ु"),
    "e":  ("ए",  "े"),
    "i":  ("इ",  "ि"),
    "u":  ("उ",  "ु"),
    "o":  ("ओ",  "ो"),
    "ɔ":  ("ऑ",  "ॉ"),  # short open-o (software, quality) — same as ɔː
    "a":  ("अ",  "ा"),
    "ɛ":  ("ए",  "े"),
    "æ":  ("ऐ",  "ै"),
    "ɒ":  ("ऑ",  "ॉ"),
    "ɑ":  ("आ",  "ा"),
}

# Consonants: IPA symbol → Devanagari base letter
_IPA_CONSONANTS: dict[str, str] = {
    # Affricates — checked before single chars
    "tʃ": "च",
    "dʒ": "ज",
    # Plosives — English alveolar t/d map to Hindi retroflex ट/ड
    # (Hindi speakers perceive English t/d as retroflex, not dental)
    "p":  "प",
    "b":  "ब",
    "t":  "ट",
    "d":  "ड",
    "k":  "क",
    "ɡ":  "ग",   # U+0261 (IPA Latin small g)
    "g":  "ग",   # ASCII g fallback
    # Fricatives
    "f":  "फ",
    "v":  "व",
    "s":  "स",
    "z":  "ज़",
    "ʃ":  "श",
    "ʒ":  "ज़",
    "h":  "ह",
    "θ":  "थ",   # "thin"
    "ð":  "द",   # "this" — dental, intentionally द not ड
    "x":  "ख़",
    # Nasals
    "m":  "म",
    "n":  "न",
    # ŋ handled specially in _ipa_to_devanagari (produces anusvara + ग)
    # Liquids & approximants
    "l":  "ल",
    "r":  "र",
    "ɹ":  "र",   # English rhotic r
    "ɾ":  "ट",   # alveolar flap — in en-us this is intervocalic /t/ (meeting, water, better)
    "w":  "व",
    "j":  "य",
}

_HALANT = "्"
_ALL_IPA = {**_IPA_VOWELS, **_IPA_CONSONANTS, "ŋ": None}  # ŋ included for tokenizer
# Characters to skip during IPA tokenization
_IPA_SKIP = frozenset("ˈˌ./[]() \t\n")


def _tokenize_ipa(ipa: str) -> list[str]:
    """Tokenize an IPA string into a list of phoneme tokens using longest-match."""
    # Remove tie bars (U+0361, U+035C) and nasalization (U+0303)
    ipa = ipa.replace("\u0361", "").replace("\u035C", "").replace("\u0303", "")
    # Drop ɹ after ɚ (both produce र, avoid double र in words like "delivery")
    ipa = ipa.replace("ɚɹ", "ɚ")
    tokens: list[str] = []
    i = 0
    while i < len(ipa):
        if ipa[i] in _IPA_SKIP:
            i += 1
            continue
        matched = False
        for length in (3, 2, 1):
            if i + length <= len(ipa):
                candidate = ipa[i: i + length]
                if candidate in _ALL_IPA:
                    tokens.append(candidate)
                    i += length
                    matched = True
                    break
        if not matched:
            i += 1  # skip unrecognised IPA character
    return tokens


def _ipa_to_devanagari(ipa: str) -> str:
    """Convert an IPA transcription to approximate Devanagari phonetic spelling.

    Handles the four syllable transitions:
    - Consonant → Vowel: consonant base + vowel matra
    - Consonant → Consonant: join with halant (virama)
    - Vowel → Consonant: independent vowel, then new syllable
    - Vowel → Vowel: independent vowel forms

    Special handling:
    - ŋ: produces anusvara (ं) on current syllable + ग for next syllable
    - ɜː/ɝ/ɚ: r-colored vowels produce र (consonant-like) for Hindi perception
    """
    tokens = _tokenize_ipa(ipa)
    if not tokens:
        return ""

    result: list[str] = []
    pending: list[str] = []  # consonant base letters waiting for a vowel

    for i, token in enumerate(tokens):
        # Special: velar nasal ŋ → anusvara + ग
        if token == "ŋ":
            # Flush pending consonants with inherent schwa + anusvara
            if pending:
                base = _HALANT.join(pending)
                result.append(base + "ं")
                pending = []
            elif result:
                # Add anusvara to the previous syllable
                result[-1] += "ं"
            # Add ग to pending ONLY if next token isn't already ɡ/g
            # (e.g. "angry" /æŋɡɹi/ has explicit ɡ after ŋ)
            next_token = tokens[i + 1] if i + 1 < len(tokens) else None
            if next_token not in ("ɡ", "g"):
                pending.append("ग")
            continue

        if token in _IPA_VOWELS:
            indep, matra = _IPA_VOWELS[token]
            if pending:
                base = _HALANT.join(pending)
                # Schwa (empty matra) = inherent vowel, just write the consonant base
                result.append(base if matra == "" else base + matra)
                pending = []
            else:
                result.append(indep)

        elif token in _IPA_CONSONANTS:
            pending.append(_IPA_CONSONANTS[token])

    # Word-final consonants: give them inherent schwa (natural for Hindi borrowed words)
    if pending:
        result.append(_HALANT.join(pending))

    out = "".join(result)

    # Word-final short i → long ī (Hindi convention for English borrowed words)
    # city→सिटी, quality→क्वॉलिटी, technology→टेक्नॉलजी
    if out.endswith("ि"):
        out = out[:-1] + "ी"
    elif out.endswith("इ"):
        out = out[:-1] + "ई"

    return out


def _get_ipa_for_words(words: list[str]) -> list[str]:
    """Get IPA transcriptions for a list of English words via espeak-ng.

    Uses a single subprocess call for efficiency. Falls back to per-word calls
    if the token count doesn't match (e.g. espeak-ng splits a word).
    Returns empty strings on any error so the caller can fall back gracefully.
    """
    if not words:
        return []
    try:
        proc = subprocess.run(
            ["espeak-ng", "-v", "en-us", "-q", "--ipa", " ".join(words)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ipa_tokens = proc.stdout.strip().split()
        if len(ipa_tokens) == len(words):
            return ipa_tokens
        # Token count mismatch — fall back to one call per word
        results: list[str] = []
        for word in words:
            p = subprocess.run(
                ["espeak-ng", "-v", "en-us", "-q", "--ipa", word],
                capture_output=True, text=True, timeout=3,
            )
            results.append(p.stdout.strip())
        return results
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # espeak-ng not available (e.g. running outside Docker) — skip silently
        return [""] * len(words)


def _normalize_english_words(text: str) -> str:
    """Replace Latin-script words in Hindi text with phonetic Devanagari.

    Called after the acronym step so ALL-CAPS words are already converted.
    Works right-to-left to preserve string positions during replacement.
    """
    matches = list(re.finditer(r"\b[a-zA-Z]+\b", text))
    if not matches:
        return text

    words = [m.group(0).lower() for m in matches]
    ipa_list = _get_ipa_for_words(words)

    for match, ipa in zip(reversed(matches), reversed(ipa_list)):
        devanagari = (_ipa_to_devanagari(ipa) if ipa else "") or match.group(0)
        text = text[: match.start()] + devanagari + text[match.end():]

    return text


# ---------------------------------------------------------------------------
# Date normalizer
# ---------------------------------------------------------------------------

def _replace_dates(text: str) -> str:
    """Detect any date format via dateparser, replace with 'D MonthName YYYY'.

    Devanagari characters are replaced with spaces (same length) before passing
    to search_dates - otherwise search_dates(languages=['en']) returns None
    when any non-Latin script is present.

    Using Hindi month name format avoids Kenpath's fraction classifier bug
    (which fires on DD/MM) and its digit-by-digit fallback for zero-padded
    DD-MM-YYYY. Kenpath receives e.g. '15 अगस्त 1947' and verbalizes naturally.
    """
    ascii_text = re.sub(r'[\u0900-\u097F]+', lambda m: ' ' * len(m.group()), text)
    results = search_dates(ascii_text, languages=["en"], settings=_DP_SETTINGS)
    if not results:
        return text
    for date_str, dt in reversed(results):
        if date_str.replace(" ", "").replace(",", "").isdigit():
            continue
        normalized_date = f"{dt.day} {HINDI_MONTHS[dt.month]} {dt.year}"
        pos = text.rfind(date_str)
        if pos != -1:
            text = text[:pos] + normalized_date + text[pos + len(date_str):]
    return text


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def normalize_hindi(text: str) -> str:
    """Normalize Hindi text for Piper TTS.

    Runs in order:
    1. Date formats -> 'D MonthName YYYY'
    2. ALL-CAPS acronyms -> Hindi letter names
    3. English words -> phonetic Devanagari (via espeak-ng IPA)
    4. Numbers, currency, time, measures -> Kenpath WFST
    """
    if not text or not text.strip():
        return text

    # 1. Dates
    text = _replace_dates(text)

    # 2. Acronyms: API -> ए पी आई
    text = re.sub(
        r'\b[A-Z]{2,}\b',
        lambda m: " ".join(LETTER_TO_HINDI.get(c, c) for c in m.group(0)),
        text,
    )

    # 3. English words -> IPA -> Devanagari
    text = _normalize_english_words(text)

    # 4. Kenpath: numbers, currency, time, measures
    text = _normalizer.normalize(text, punct_post_process=True)

    return " ".join(text.split())


def warmup() -> None:
    """Pre-compile Kenpath grammars and dateparser. Call once at startup."""
    normalize_hindi("नमस्ते 15/08/2024 और ₹500")
