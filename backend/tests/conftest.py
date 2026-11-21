"""Shared fixtures: an isolated app with a fake LLM client and fake embeddings."""
import hashlib
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ADMIN_USER = "test_admin"
ADMIN_PASSWORD = "test-admin-password"


class FakeEmbeddings:
    """Deterministic bag-of-words embeddings (no network)."""

    DIM = 64

    def _vec(self, text):
        vec = [0.0] * self.DIM
        for word in text.lower().split():
            idx = int(hashlib.md5(word.strip(".,?!:;").encode()).hexdigest(), 16) % self.DIM
            vec[idx] += 1.0
        return vec

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeOpenAI:
    """Mimics the subset of the OpenAI client used by the app and records prompts."""

    def __init__(self):
        self.prompts = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, model, input):
        self.prompts.append(input)
        return SimpleNamespace(output_text="FAKE LLM ANSWER", output=[])


@pytest.fixture()
def fake_llm():
    return FakeOpenAI()


@pytest.fixture()
def app(tmp_path, monkeypatch, fake_llm):
    from config import reset_config

    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    monkeypatch.setenv("ADMIN_USERNAME", ADMIN_USER)
    monkeypatch.setenv("ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.db"))
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path / "documents"))
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("CONTACTS_DB_FILE", str(tmp_path / "contacts.db"))
    monkeypatch.setenv("MAX_FILE_SIZE", str(50 * 1024))
    monkeypatch.delenv("VERCEL", raising=False)
    reset_config()

    from app import create_app

    flask_app = create_app(
        test_config={
            "TESTING": True,
            "SESSION_TYPE": "filesystem",
            "SESSION_FILE_DIR": str(tmp_path / "sessions"),
        },
        rag_overrides={"openai_client": fake_llm, "embeddings": FakeEmbeddings()},
    )
    yield flask_app
    reset_config()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['access_token']}"}


@pytest.fixture()
def user_headers(client):
    resp = client.post("/api/auth/register", json={"username": "plainuser", "password": "secret123"})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.get_json()['access_token']}"}
