"""TTS engine: model loading and inference via Piper (ONNX Runtime on CPU)."""

import io
import time
import wave
from pathlib import Path
from typing import Optional

from piper.config import SynthesisConfig
from piper.voice import PiperVoice

from src.config import AVAILABLE_MODELS, DEFAULT_MODEL
from src.tts.normalizer import normalize_hindi


class TTSEngine:
    """Wraps Piper TTS voices. Loads models on demand and caches them."""

    def __init__(self) -> None:
        self._voices: dict[str, PiperVoice] = {}
        self._latency_history: list[float] = []

    def load(self, model_name: str = DEFAULT_MODEL) -> None:
        """Pre-load a model into cache (call at startup for warm-up)."""
        self._get_voice(model_name)

    def _get_voice(self, model_name: str) -> PiperVoice:
        if model_name not in self._voices:
            if model_name not in AVAILABLE_MODELS:
                raise ValueError(
                    f"Unknown model '{model_name}'. "
                    f"Available: {list(AVAILABLE_MODELS)}"
                )
            onnx_path = AVAILABLE_MODELS[model_name]
            config_path = Path(str(onnx_path) + ".json")
            self._voices[model_name] = PiperVoice.load(
                str(onnx_path), config_path=str(config_path), use_cuda=False
            )
        return self._voices[model_name]

    def synthesize_pcm(
        self,
        text: str,
        model_name: str = DEFAULT_MODEL,
        speed: float = 1.0,
    ) -> tuple[bytes, int, int, int]:
        """Synthesize text to raw PCM bytes (no WAV header).

        Returns (pcm_bytes, sample_rate, channels, sample_width).
        Used by the streaming endpoint — caller owns the WAV header.
        """
        voice = self._get_voice(model_name)
        normalized = normalize_hindi(text)

        syn_config = SynthesisConfig(length_scale=1.0 / speed)
        chunks = list(voice.synthesize(normalized, syn_config=syn_config))

        if not chunks:
            return b'', 22050, 1, 2

        pcm = b''.join(c.audio_int16_bytes for c in chunks)
        return pcm, chunks[0].sample_rate, chunks[0].sample_channels, chunks[0].sample_width

    def synthesize_wav(
        self,
        text: str,
        model_name: str = DEFAULT_MODEL,
        speed: float = 1.0,
    ) -> tuple[bytes, float]:
        """Synthesize text to WAV bytes.

        Returns (wav_bytes, inference_time_ms).
        """
        voice = self._get_voice(model_name)
        normalized = normalize_hindi(text)

        t0 = time.perf_counter()
        syn_config = SynthesisConfig(length_scale=1.0 / speed)
        chunks = list(voice.synthesize(normalized, syn_config=syn_config))
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if not chunks:
            raise RuntimeError("Piper produced no audio chunks")

        buf = io.BytesIO()
        with wave.open(buf, "w") as wf:
            wf.setnchannels(chunks[0].sample_channels)
            wf.setsampwidth(chunks[0].sample_width)
            wf.setframerate(chunks[0].sample_rate)
            for chunk in chunks:
                wf.writeframes(chunk.audio_int16_bytes)

        self._latency_history.append(elapsed_ms)
        if len(self._latency_history) > 50:
            self._latency_history.pop(0)

        return buf.getvalue(), elapsed_ms

    @property
    def avg_latency_ms(self) -> Optional[float]:
        if not self._latency_history:
            return None
        return round(sum(self._latency_history) / len(self._latency_history), 1)
