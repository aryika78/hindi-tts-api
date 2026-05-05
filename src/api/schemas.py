"""Pydantic request/response models for the TTS API."""

from typing import Literal
from pydantic import BaseModel, Field

from src.config import DEFAULT_MODEL


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Hindi text to synthesize")
    format: Literal["wav"] = Field("wav", description="Output audio format")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Speech speed multiplier")
    model: str = Field(DEFAULT_MODEL, description="Voice model to use")


class HealthResponse(BaseModel):
    status: str
    model: str
    device: str
    available_models: list[str]
    avg_latency_ms: float | None
