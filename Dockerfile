# Hindi TTS API - CPU-only, no GPU required
# Python 3.11 (Kenpath requires 3.10-3.12)
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps: build tools + espeak-ng (for Piper G2P)
# Note: pynini ships manylinux wheels that bundle OpenFST - no system libopenfst needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps in order (pynini needs OpenFST headers at compile time)
RUN pip install --no-cache-dir --timeout 300 --retries 5 "pynini>=2.1.7"

# Install Kenpath from source (not on PyPI)
RUN git clone --depth 1 https://github.com/Kenpath/indic-text-normalization.git /opt/kenpath \
    && pip install --no-cache-dir -e /opt/kenpath

# Install rest of dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-compile Kenpath WFST grammars for Hindi at build time
# This avoids the 2-5s compile cost on first request
RUN python -c "from indic_text_normalization import Normalizer; Normalizer(lang='hi', input_case='cased'); print('Kenpath Hindi grammars compiled OK')"

# Copy app source
COPY src/ src/
COPY models/ models/

# Expose API port
EXPOSE 8000

# Run with uvicorn - single worker (model is not thread-safe, use 1 worker per container)
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
