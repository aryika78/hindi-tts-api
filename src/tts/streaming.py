"""Sentence splitting and streaming WAV utilities for chunked TTS synthesis."""

import re
import struct

# Split on sentence-ending punctuation — keeps delimiter attached to preceding chunk
_SENTENCE_END = re.compile(r'(?<=[।?!\n])\s*')


def split_into_sentences(text: str, max_len: int = 200) -> list[str]:
    """Split Hindi text at natural linguistic boundaries.

    Strategy:
    1. Primary split on sentence-enders: । ? ! newline
    2. Secondary split on commas for chunks still over max_len
    3. Merge chunks under 3 words into the next one (avoids tiny audio clips)
    """
    # Step 1: primary split
    chunks = [c.strip() for c in _SENTENCE_END.split(text) if c.strip()]

    # Step 2: break up chunks that are still too long, split on comma
    expanded: list[str] = []
    for chunk in chunks:
        if len(chunk) > max_len:
            parts = [p.strip() for p in chunk.split(',') if p.strip()]
            expanded.extend(parts)
        else:
            expanded.append(chunk)

    # Step 2b: last resort — split on nearest space if still over max_len
    final: list[str] = []
    for chunk in expanded:
        while len(chunk) > max_len:
            # Find the last space before the max_len cutoff
            split_at = chunk.rfind(' ', 0, max_len)
            if split_at == -1:
                break  # no space found, can't split further
            final.append(chunk[:split_at].strip())
            chunk = chunk[split_at:].strip()
        if chunk:
            final.append(chunk)
    expanded = final

    # Step 3: merge forward any chunk that is too short (< 3 words)
    result: list[str] = []
    i = 0
    while i < len(expanded):
        chunk = expanded[i]
        while i + 1 < len(expanded) and len(chunk.split()) < 3:
            i += 1
            chunk = chunk + ' ' + expanded[i]
        result.append(chunk)
        i += 1

    return result


def make_streaming_wav_header(sample_rate: int, channels: int, sample_width: int) -> bytes:
    """WAV header with 0xFFFFFFFF size fields — signals unknown/streaming length.

    All major browsers, media players, and audio libraries handle this correctly.
    The actual PCM data is appended after this header as chunks arrive.
    """
    UNKNOWN = 0xFFFFFFFF
    return struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', UNKNOWN,                               # RIFF chunk, unknown size
        b'WAVE',
        b'fmt ', 16, 1,                                 # PCM format
        channels,
        sample_rate,
        sample_rate * channels * sample_width,          # byte rate
        channels * sample_width,                        # block align
        sample_width * 8,                               # bits per sample
        b'data', UNKNOWN,                               # data chunk, unknown size
    )
