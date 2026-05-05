"""FastAPI app entry point with model warm-up on startup."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.routes.synthesize import router as synthesize_router
from src.api.schemas import HealthResponse
from src.config import AVAILABLE_MODELS, DEFAULT_MODEL
from src.tts.engine import TTSEngine
from src.tts.normalizer import warmup as normalizer_warmup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load and warm up the default TTS model on startup."""
    normalizer_warmup()
    logger.info("Kenpath normalizer warmed up.")
    engine = TTSEngine()
    engine.load(DEFAULT_MODEL)
    app.state.engine = engine
    logger.info("Model '%s' loaded and warmed up.", DEFAULT_MODEL)
    yield
    # cleanup (none needed for ONNX)


app = FastAPI(
    title="Indic TTS API",
    description="Low-latency Hindi Text-to-Speech API (Piper VITS + ONNX)",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(synthesize_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def demo_ui():
    """Browser-based demo page for testing the TTS API."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="hi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hindi TTS Demo</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 700px; margin: 60px auto; padding: 0 20px; background: #f5f5f5; }
    h1 { color: #333; }
    textarea { width: 100%; height: 120px; font-size: 18px; padding: 12px; border: 1px solid #ccc; border-radius: 6px; resize: vertical; }
    .controls { display: flex; gap: 12px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
    select { padding: 10px; font-size: 15px; border-radius: 6px; border: 1px solid #ccc; }
    button { padding: 12px 28px; font-size: 16px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #93c5fd; cursor: not-allowed; }
    audio { margin-top: 20px; width: 100%; }
    .status { margin-top: 12px; color: #555; font-size: 14px; }
    .error { color: #dc2626; }
    .samples { margin-top: 30px; }
    .samples h3 { color: #555; font-size: 14px; margin-bottom: 8px; }
    .chip { display: inline-block; background: #e2e8f0; padding: 6px 12px; border-radius: 20px; margin: 4px; cursor: pointer; font-size: 14px; }
    .chip:hover { background: #cbd5e1; }
  </style>
</head>
<body>
  <h1>Hindi TTS Demo</h1>
  <textarea id="text" placeholder="यहाँ हिंदी में टाइप करें...">नमस्ते, आप कैसे हैं?</textarea>
  <div class="controls">
    <select id="model">
      <option value="pratham-medium">Pratham (Male)</option>
    </select>
    <select id="speed">
      <option value="0.75">Slow</option>
      <option value="1.0" selected>Normal</option>
      <option value="1.25">Fast</option>
      <option value="1.5">Faster</option>
    </select>
    <button id="btn" onclick="synthesize()">Speak</button>
    <label style="display:flex;align-items:center;gap:6px;font-size:14px;cursor:pointer">
      <input type="checkbox" id="streaming" checked> Streaming
    </label>
  </div>
  <div class="status" id="status"></div>
  <audio id="player" controls style="display:none"></audio>

  <div class="samples">
    <h3>Try these examples:</h3>
    <span class="chip" onclick="setText('इस गाँव में 250 लोग रहते हैं।')">Number: 250</span>
    <span class="chip" onclick="setText('यह किताब 500 रुपये की है।')">Currency: ₹500</span>
    <span class="chip" onclick="setText('आज 15/08/1947 की याद है।')">Date: 15/08/1947</span>
    <span class="chip" onclick="setText('मेरा नंबर 9313894476 है।')">Phone number</span>
    <span class="chip" onclick="setText('मीटिंग 12:30 बजे है।')">Time: 12:30</span>
    <span class="chip" onclick="setText('यह API सर्वर है।')">Acronym: API</span>
    <span class="chip" onclick="setText('भारत एक विशाल और विविध देश है। यहाँ की संस्कृति हजारों साल पुरानी है। इस देश में 140 करोड़ से अधिक लोग रहते हैं। हिंदी यहाँ की राजभाषा है, लेकिन यहाँ सैकड़ों भाषाएँ बोली जाती हैं। भारत की राजधानी नई दिल्ली है। मुंबई यहाँ का सबसे बड़ा शहर है। यह दुनिया का सबसे बड़ा लोकतंत्र है।')">Long text (streaming)</span>
  </div>

  <script>
    function setText(t) { document.getElementById('text').value = t; }

    async function synthesize() {
      const text = document.getElementById('text').value.trim();
      if (!text) return;
      const btn = document.getElementById('btn');
      const status = document.getElementById('status');
      const player = document.getElementById('player');
      const useStreaming = document.getElementById('streaming').checked;
      btn.disabled = true;
      btn.textContent = 'Generating...';
      status.textContent = '';
      status.className = 'status';
      const model = document.getElementById('model').value;
      const speed = parseFloat(document.getElementById('speed').value);
      const t0 = Date.now();

      try {
        if (useStreaming) {
          // Streaming: set audio src to GET endpoint directly — browser streams as it arrives
          const url = '/synthesize/stream?text=' + encodeURIComponent(text) +
                      '&model=' + encodeURIComponent(model) +
                      '&speed=' + speed;
          player.src = url;
          player.style.display = 'block';
          player.play();
          player.oncanplay = () => {
            status.textContent = 'Streaming — first audio in ' + Math.round(Date.now() - t0) + 'ms';
          };
        } else {
          const res = await fetch('/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, model, speed })
          });
          if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Request failed');
          }
          const blob = await res.blob();
          const latency = res.headers.get('x-inference-time-ms');
          player.src = URL.createObjectURL(blob);
          player.style.display = 'block';
          player.play();
          status.textContent = 'Done in ' + Math.round(Date.now() - t0) + 'ms (inference: ' + latency + 'ms)';
        }
      } catch (e) {
        status.textContent = 'Error: ' + e.message;
        status.className = 'status error';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Speak';
      }
    }

    document.getElementById('text').addEventListener('keydown', e => {
      if (e.ctrlKey && e.key === 'Enter') synthesize();
    });
  </script>
</body>
</html>""")


@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Return server health and latency stats."""
    engine: TTSEngine = request.app.state.engine
    return HealthResponse(
        status="ok",
        model=DEFAULT_MODEL,
        device="cpu",
        available_models=list(AVAILABLE_MODELS.keys()),
        avg_latency_ms=engine.avg_latency_ms,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})
