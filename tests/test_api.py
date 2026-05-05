"""API endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------- /health ----------

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["device"] == "cpu"
    assert "pratham-medium" in data["available_models"]


# ---------- /synthesize ----------

def test_synthesize_basic_hindi(client):
    r = client.post("/synthesize", json={"text": "नमस्ते, आप कैसे हैं?"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert float(r.headers["x-inference-time-ms"]) > 0
    assert len(r.content) > 1000  # non-trivial audio


def test_synthesize_number(client):
    r = client.post("/synthesize", json={"text": "इस गाँव में 250 लोग रहते हैं।"})
    assert r.status_code == 200
    assert len(r.content) > 1000


def test_synthesize_phone(client):
    r = client.post("/synthesize", json={"text": "मेरा फोन नंबर 9313894476 है।"})
    assert r.status_code == 200


def test_synthesize_acronym(client):
    r = client.post("/synthesize", json={"text": "यह API सर्वर है।"})
    assert r.status_code == 200


def test_synthesize_date(client):
    r = client.post("/synthesize", json={"text": "आज 15/08/1947 की याद है।"})
    assert r.status_code == 200


def test_synthesize_default_model(client):
    r = client.post("/synthesize", json={"text": "नमस्ते।", "model": "pratham-medium"})
    assert r.status_code == 200


def test_synthesize_speed(client):
    r = client.post("/synthesize", json={"text": "नमस्ते।", "speed": 1.5})
    assert r.status_code == 200


def test_synthesize_unknown_model(client):
    r = client.post("/synthesize", json={"text": "नमस्ते।", "model": "unknown-model"})
    assert r.status_code == 400


def test_synthesize_empty_text(client):
    r = client.post("/synthesize", json={"text": ""})
    assert r.status_code == 422  # Pydantic validation rejects empty string


def test_health_shows_latency_after_requests(client):
    client.post("/synthesize", json={"text": "परीक्षण।"})
    r = client.get("/health")
    data = r.json()
    assert data["avg_latency_ms"] is not None
    assert data["avg_latency_ms"] > 0


# ---------- /synthesize/stream ----------

def test_stream_get(client):
    r = client.get("/synthesize/stream", params={"text": "नमस्ते।"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert len(r.content) > 100  # has WAV header + some audio


def test_stream_post(client):
    r = client.post("/synthesize/stream", json={"text": "नमस्ते, आप कैसे हैं?"})
    assert r.status_code == 200
    assert len(r.content) > 100


def test_stream_long_text(client):
    text = "भारत एक विशाल देश है। यहाँ की संस्कृति पुरानी है। हिंदी राजभाषा है।"
    r = client.get("/synthesize/stream", params={"text": text})
    assert r.status_code == 200
    assert len(r.content) > 5000  # multiple sentences = more audio


def test_stream_with_english(client):
    r = client.get("/synthesize/stream", params={"text": "यह machine learning है।"})
    assert r.status_code == 200
    assert len(r.content) > 100
