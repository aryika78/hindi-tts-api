# Design Decisions

## The Core Problem

Piper TTS speaks Hindi perfectly — but only if you give it pure Hindi text. Real-world Hindi has numbers, dates, English words, and acronyms mixed in. Piper doesn't know what to do with "machine learning" or "250" or "API" — it either skips them or produces garbage audio.

No single library solves all of this for Hindi. So the main challenge was building a text preprocessing pipeline that converts messy real-world Hindi text into clean Devanagari that Piper can actually speak.

---

## Model Selection

### What I tried

| Model | Speed (CPU) | Hindi Quality | Fine-tunable? |
|---|---|---|---|
| **Piper (pratham-medium)** | ~120ms/sentence | Clear, natural | No |
| Piper (rohan) | ~120ms/sentence | Noticeably worse | Yes (.ckpt exists) |
| Coqui XTTS v2 | 5-15s/sentence | Very good | Yes |
| Meta MMS-TTS | 2-5s/sentence | Moderate | Yes |
| Silero | ~200ms/sentence | No Hindi support | — |

### Why pratham-medium?

I picked pratham because it's the only model that's both fast enough for a real-time API AND sounds good. Rohan has a training checkpoint so it can be fine-tuned, but the base voice quality is clearly worse — and fine-tuning it to match pratham's clarity would be a gamble with no guarantee.

The other models (Coqui, MMS) sound fine but take 5-15 seconds per sentence on CPU. That kills any real-time use case.

### Why not fine-tune?

I looked into this seriously:

1. **Pratham's training checkpoint was never published.** It's only available as ONNX — that's a frozen inference format, you can't fine-tune it. I checked HuggingFace, GitHub, Piper's releases — it doesn't exist anywhere.

2. **Fine-tuning wouldn't have solved the actual problem anyway.** Piper is a phoneme-based model. It reads Devanagari characters, not English. Even if I fine-tuned it on English words, it wouldn't learn English phonemes — that's not how the architecture works. The real fix is converting English → Devanagari BEFORE it reaches Piper.

3. **Rohan can be fine-tuned but starts from a worse place.** The only Hindi Piper voice with a .ckpt is rohan, and its base quality is noticeably worse than pratham. Fine-tuning to improve English pronunciation on a model that already has weaker Hindi pronunciation didn't make sense.

So instead of fine-tuning, I built a text preprocessing pipeline that solves the problem at the right layer.

---

## The Text Preprocessing Pipeline

This is the main technical work of the project. There's no off-the-shelf solution for "take Hindi text with English words and numbers and make it speakable." I had to combine multiple tools and write custom logic to fill the gaps.

### Pipeline order (and why the order matters)

```
Raw text → Dates → Acronyms → English words → Numbers/currency → Clean Hindi → Piper
```

The order isn't random:
- **Dates go first** because they contain digits. If numbers run first, "15/08/1947" becomes "पंद्रह/शून्य आठ/उन्नीस सौ..." — broken.
- **Acronyms before English words** because "API" should be spelled out (ए पी आई), not phonetically converted (which would give something weird). After the acronym step removes ALL-CAPS words, the English word step only sees regular English words.
- **Numbers go last** (via Kenpath) so they handle whatever digits remain after dates are already processed.

### Step 1: Dates

I use `dateparser` to detect dates in any format (DD/MM/YYYY, DD-MM-YYYY, etc.) and rewrite them as "15 अगस्त 1947" with Hindi month names.

**The workaround:** dateparser breaks when the text has Devanagari characters mixed in — it just returns nothing. So I temporarily replace all Devanagari characters with spaces (keeping the same string length so positions stay correct), run dateparser on that, then use the detected positions to replace dates in the original text.

I also convert to Hindi month name format (not DD/MM/YYYY) because Kenpath's number normalizer has a bug — it sees DD/MM as a fraction and reads it as "पंद्रह बटा आठ" instead of a date.

### Step 2: Acronyms

Simple — detect 2+ uppercase English letters (regex: `\b[A-Z]{2,}\b`) and spell each letter out in Hindi. "API" → "ए पी आई", "ONNX" → "ओ एन एन एक्स".

### Step 3: English words → Devanagari (the hard part)

This was the biggest piece of work. There's no library that converts English words to how Hindi speakers actually say them.

**How it works:**
1. Find all remaining Latin-script words in the text (regex)
2. Send them to `espeak-ng` which outputs IPA pronunciation (International Phonetic Alphabet) — e.g., "machine" → `məˈʃiːn`
3. Convert IPA to Devanagari using a phoneme mapper I built from scratch

**Why I couldn't just use a transliteration library:**
Transliteration maps letters, not sounds. "machine" transliterated letter-by-letter gives "माचिने" — that's wrong. Hindi speakers say "मशीन". To get the right pronunciation, you need to go through the actual phonetics.

**Building the IPA → Devanagari converter:**

No library exists for this, so I built it. It maps all 42 IPA symbols that espeak-ng produces for English into Devanagari. Some of the non-obvious decisions:

- **English t/d → ट/ड (retroflex), not त/द (dental):** This is how Hindi speakers actually hear English t and d. If you say "digital" in Hindi, it's "डिजिटल" with retroflex ड and ट, not dental द and त. This one change fixed dozens of words.

- **The flap sound (ɾ) → ट:** In American English, the "t" in words like "meeting", "water", "better" is pronounced as a flap (ɾ) — a quick tap. Hindi speakers hear this as ट. So "meeting" (mˈiːɾɪŋ) → मीटिंग, "water" (wˈɔːɾɚ) → वॉटर. Without this mapping, they came out as "मीरिंग" and "वॉरर" which sound wrong.

- **R-colored vowels (ɜː, ɚ) → र:** English has vowels that sound like "er" — "server" (sˈɜːvɚ), "learning" (lˈɜːnɪŋ). Hindi doesn't have these vowels, but Hindi speakers hear them as the consonant र. So "server" → सर्वर, "learning" → लर्निंग. Getting this right required treating these "vowels" as consonants in the Devanagari generation logic.

- **The "ng" sound (ŋ):** This needed special handling. In Hindi, the "ng" sound is written as anusvara (ं) + ग. But in words like "angry" (æŋɡɹi), espeak-ng outputs both ŋ and ɡ — if I naively convert both, I get "ंगग" (double ग). So the converter looks ahead: if the next IPA token is already ɡ, it only adds the anusvara and lets the existing ɡ handle the rest.

- **Word-final short i → long ī:** Hindi convention for borrowed English words — "city" ends with ई not इ, "quality" ends with ई not इ. I detect this at the end and convert automatically.

- **Duplicate र prevention:** Some words (like "delivery") produce ɚɹ in IPA — both map to र, giving double र. I added a dedup step: ɚɹ → ɚ before tokenization.

- **Consonant clusters with halant:** When multiple consonants come together without a vowel between them (like "str" in "streaming"), they get joined with halant (्) — the virama that suppresses the inherent vowel. "streaming" → स्ट्रीमिंग. The converter tracks "pending consonants" and joins them when a vowel finally appears.

**The tokenizer matters too.** IPA has multi-character symbols — "tʃ" is one sound (च), not t + ʃ. Same for diphthongs like "aɪ" (ऐ). The tokenizer uses longest-match: it tries 3-character sequences first, then 2, then 1, so it always picks the right phoneme boundary.

**Batched espeak-ng calls:** Instead of calling espeak-ng once per word (which is slow with subprocess overhead), I batch all English words into a single call. If espeak-ng splits a word unexpectedly and the token count doesn't match, it falls back to one-call-per-word automatically.

### Step 4: Numbers, currency, time

Handled by Kenpath (indic-text-normalization), a WFST-based normalizer. It converts:
- `250` → `दो सौ पचास`
- `₹500` → `पाँच सौ रुपए`
- `12:30` → `बारह बजकर तीस मिनट`

I run this last so it only sees digits that weren't already handled by the date step.

---

## Streaming

For long text, waiting for the entire paragraph to synthesize before playing audio would be slow (~1.5s for 7 sentences). So I built sentence-by-sentence streaming:

1. Split the text at sentence boundaries (। ? ! newline)
2. Send a WAV header with 0xFFFFFFFF (unknown size) — this tells the browser "I don't know how long this will be, just keep playing"
3. Synthesize each sentence and stream the PCM audio as it's ready
4. First audio arrives in ~177ms regardless of total text length

**The sentence splitter has 3 fallback levels:**
- First: split on sentence-ending punctuation (। ? !)
- If a chunk is still too long (>200 chars): split on commas
- If still too long (no commas): split on the nearest space
- Then: merge any tiny chunks (<3 words) into the next one — because 2-word audio clips sound choppy

---

## What's NOT perfect (being honest)

- **Acronyms like "WiFi", "FastAPI"** — mixed-case words don't match the ALL-CAPS regex, so they go through the IPA path instead of being spelled out. The IPA pronunciation is okay but not ideal ("WiFi" → "वैफै" instead of "वाई-फाई").
- **Some consonant clusters** — English has combinations that don't exist in Hindi. The converter approximates them but it's not always perfect.
- **espeak-ng dependency** — the English word conversion requires espeak-ng installed as a system package. Without it, English words pass through unchanged (graceful fallback, doesn't crash).
