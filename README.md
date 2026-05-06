# Hindi TTS API

Low-latency Hindi Text-to-Speech API built on **Piper VITS** (ONNX Runtime, CPU-only). Handles numbers, dates, currency, acronyms, and English words mixed in Hindi text.

---

## Features

- **POST /synthesize** — returns WAV audio for any Hindi text
- **GET/POST /synthesize/stream** — streams audio sentence-by-sentence (first audio in ~177ms)
- **GET /health** — server status with rolling average latency
- **GET /** — browser demo page with examples, speed control, and streaming toggle
- **Text normalizer** — numbers, dates, currency, phone numbers, acronyms → spoken Hindi
- **English word handling** — English words in Hindi text are converted to phonetic Devanagari via espeak-ng IPA before synthesis
- **CPU-only** — no GPU required, runs on any machine or container

---

## Latency (measured on Docker, CPU)

| Input | Words | Avg latency |
|---|---|---|
| Short sentence | 5 | ~120ms |
| Medium sentence | 15 | ~350ms |
| Hindi + English mix | 10 | ~275ms |
| Long paragraph (7 sentences) | 56 | ~1490ms (full) / **177ms** (streaming first audio) |

Streaming splits text at sentence boundaries and starts playing while remaining sentences are still being synthesized.

---

## Quick Start

### Run with Docker (recommended)

```bash
docker build -t hindi-tts-api .
docker run -p 8000:8000 hindi-tts-api
```

Open `http://localhost:8000` in your browser for the demo UI.

### Run locally (Linux/Mac)

```bash
# System deps
sudo apt-get install -y espeak-ng build-essential

# Python deps
pip install pynini>=2.1.7
git clone --depth 1 https://github.com/Kenpath/indic-text-normalization.git
pip install -e ./indic-text-normalization
pip install -r requirements.txt

# Start
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

---

## API Reference

### POST /synthesize

Returns WAV audio for the given Hindi text.

**Request body (JSON):**

| Field | Type | Default | Description |
|---|---|---|---|
| `text` | string | required | Hindi text to synthesize |
| `model` | string | `pratham-medium` | Voice model name |
| `speed` | float | `1.0` | Speech rate (0.5 – 2.0) |

**Response:** WAV audio bytes

**Headers:** `X-Inference-Time-Ms` — synthesis time in milliseconds

```bash
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "नमस्ते, आप कैसे हैं?"}' \
  --output output.wav
```

### GET /synthesize/stream

Streams audio as it's generated. Use this for long text — first audio arrives in ~177ms regardless of total length.

```bash
curl "http://localhost:8000/synthesize/stream?text=भारत+एक+विशाल+देश+है।+यहाँ+की+संस्कृति+पुरानी+है।" --output stream.wav
```

Also available as POST with JSON body.

### GET /health

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "model": "pratham-medium",
  "device": "cpu",
  "available_models": ["pratham-medium"],
  "avg_latency_ms": 245.3
}
```

### Interactive API Docs (Swagger)

FastAPI auto-generates interactive API documentation at:

```
http://localhost:8000/docs
```

You can test all endpoints directly from the browser — fill in parameters, hit "Execute", and see responses.

---

## Text Normalization Pipeline

Raw Hindi text often has digits, dates, and English words that the TTS model can't read directly. The normalizer converts them to readable Hindi before synthesis.

**Steps (in order):**

1. **Dates** — any format (DD/MM/YYYY, DD-MM-YYYY, "15 August 1947") → detected by `dateparser` → rewritten as `15 अगस्त 1947` → Kenpath verbalizes it

2. **Acronyms** — 2+ uppercase letters spelled out: `API` → `ए पी आई`, `ISRO` → `आई एस आर ओ`

3. **English words** — Latin-script words are sent to `espeak-ng` to get IPA (phonetic) pronunciation, then converted to Devanagari: `machine learning` → `मशीन लर्निंग`, `streaming` → `स्ट्रीमिंग`

4. **Numbers, currency, time** — handled by Kenpath WFST normalizer: `250` → `दो सौ पचास`, `₹500` → `पाँच सौ रुपए`, `12:30` → `बारह बजकर तीस मिनट`

**Known limitations:**
- `₹NUMBER करोड़/लाख` — Kenpath mishandles the rupee sign placement. Workaround: write `1800 करोड़ रुपये` without ₹.

---

## Project Structure

```
├── Dockerfile
├── requirements.txt
├── DESIGN.md                            # Model selection rationale
├── .gitignore
├── models/
│   ├── pratham-medium.onnx           # Piper VITS voice model
│   └── pratham-medium.onnx.json
├── src/
│   ├── config.py                     # Model paths and settings
│   ├── api/
│   │   ├── main.py                   # FastAPI app, /health, demo UI
│   │   ├── schemas.py                # Request/response models
│   │   └── routes/
│   │       └── synthesize.py         # /synthesize and /synthesize/stream
│   └── tts/
│       ├── engine.py                 # Piper model loader and synthesis
│       ├── normalizer.py             # Hindi text normalizer + IPA→Devanagari
│       └── streaming.py              # Sentence splitting and WAV streaming
└── tests/
    ├── test_api.py                   # API endpoint tests (pytest)
    └── test_normalizer.py            # IPA→Devanagari converter tests
```

---

## Model Files

The `pratham-medium.onnx` model (63MB) is included in the repo for zero-setup Docker builds. Originally from [Piper voices](https://huggingface.co/rhasspy/piper-voices/tree/main/hi/hi_IN/pratham/medium).

---

## Running Tests

```bash
pytest tests/
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `piper-tts` | VITS speech synthesis |
| `onnxruntime` | CPU inference |
| `fastapi` + `uvicorn` | API server |
| `pynini` + `indic-text-normalization` | Kenpath WFST text normalizer |
| `dateparser` | Date detection |
| `espeak-ng` (system) | English word pronunciation (IPA) |
