"""Centralized configuration for Indic TTS."""

from pathlib import Path

# Project root
ROOT_DIR = Path(__file__).parent.parent

# Model directory
MODELS_DIR = ROOT_DIR / "models"

# Default model
DEFAULT_MODEL = "pratham-medium"

# Available models (name -> onnx file stem)
AVAILABLE_MODELS = {
    "pratham-medium": MODELS_DIR / "pratham-medium.onnx",
}

# API settings
API_HOST = "0.0.0.0"
API_PORT = 8000

# TTS settings
DEFAULT_SPEED = 1.0
DEFAULT_FORMAT = "wav"
