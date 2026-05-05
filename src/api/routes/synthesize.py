"""Synthesis endpoints: POST /synthesize, GET+POST /synthesize/stream."""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from src.api.schemas import SynthesizeRequest
from src.config import DEFAULT_MODEL
from src.tts.streaming import make_streaming_wav_header, split_into_sentences

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/synthesize/stream")
async def synthesize_stream_get(
    request: Request,
    text: str = Query(..., min_length=1, max_length=5000),
    model: str = Query(DEFAULT_MODEL),
    speed: float = Query(1.0, ge=0.5, le=2.0),
) -> StreamingResponse:
    """GET version of streaming synthesis — lets browser <audio> src stream directly."""
    return _stream_response(request.app.state.engine, text, model, speed)


@router.post("/synthesize/stream")
async def synthesize_stream(request: Request, body: SynthesizeRequest) -> StreamingResponse:
    """Synthesize Hindi text as a streaming WAV response.

    Splits text at sentence/clause boundaries and streams each chunk as it is
    synthesized. First audio arrives in ~177ms regardless of total text length.
    The WAV header uses 0xFFFFFFFF (unknown size) for streaming compatibility.
    """
    return _stream_response(request.app.state.engine, body.text, body.model, body.speed)


def _stream_response(engine, text: str, model: str, speed: float) -> StreamingResponse:
    # Validate model before entering generator (so bad model returns 400, not 500)
    try:
        engine._get_voice(model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    sentences = split_into_sentences(text)

    def generate():
        header_sent = False
        for sentence in sentences:
            if not sentence.strip():
                continue
            try:
                pcm, sample_rate, channels, sample_width = engine.synthesize_pcm(
                    text=sentence,
                    model_name=model,
                    speed=speed,
                )
            except Exception as exc:
                logger.warning("Skipped sentence: %s — %s", sentence, exc)
                continue

            if not pcm:
                continue

            if not header_sent:
                yield make_streaming_wav_header(sample_rate, channels, sample_width)
                header_sent = True

            yield pcm

    return StreamingResponse(generate(), media_type="audio/wav")


@router.post("/synthesize")
async def synthesize(request: Request, body: SynthesizeRequest) -> Response:
    """Synthesize Hindi text to audio.

    Returns WAV audio bytes with X-Inference-Time-Ms header.
    """
    engine = request.app.state.engine

    try:
        wav_bytes, latency_ms = engine.synthesize_wav(
            text=body.text,
            model_name=body.model,
            speed=body.speed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"X-Inference-Time-Ms": str(round(latency_ms, 1))},
    )
