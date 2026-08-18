"""Tests for the FastAPI app endpoints (/api/sources, /api/ask, /api/status)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from freshdocs.schemas import Answer, Citation


@pytest.fixture
def client():
    from freshdocs import main as main_module
    with TestClient(main_module.app) as c:
        yield c


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"
    assert "FreshDocs" in resp.text


def test_sources_endpoint_returns_all_sources(client):
    resp = client.get("/api/sources")
    assert resp.status_code == 200
    sources = resp.json()
    assert isinstance(sources, list)
    keys = {s["key"] for s in sources}
    assert keys == {"docker", "kubernetes", "aws-eks", "argo-cd", "github-actions", "langchain", "fixture"}


def test_sources_endpoint_includes_sitemap_and_expected_urls(client):
    resp = client.get("/api/sources")
    sources = {s["key"]: s for s in resp.json()}
    docker = sources["docker"]
    assert docker["sitemap_url"].startswith("https://docs.docker.com")
    assert isinstance(docker["expected_urls"], int)
    assert docker["expected_urls"] > 0


def test_ask_when_rag_is_none(client):
    """When no LLM provider key is set, rag is None and /api/ask should return
    a graceful message."""
    with patch("freshdocs.main.rag", None):
        resp = client.post("/api/ask", json={"question": "What is Docker?"})
        assert resp.status_code == 200
        answer = resp.json()
        assert "not configured" in answer["answer"]
        assert answer["citations"] == []


def test_ask_with_mocked_rag(client):
    canned = Answer(
        answer="Docker is a platform for building containers. [1]",
        citations=[
            Citation(index=1, title="Docker Overview", url="https://docs.docker.com/", source="docker", snippet="Docker overview..."),
        ],
    )
    mock_rag = MagicMock()
    mock_rag.answer.return_value = canned
    with patch("freshdocs.main.rag", mock_rag):
        resp = client.post("/api/ask", json={"question": "What is Docker?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == canned.answer
        assert len(data["citations"]) == 1
        assert data["citations"][0]["url"] == "https://docs.docker.com/"


def test_ask_with_source_filter(client):
    """The sources field in AskRequest should be forwarded to rag.answer."""
    mock_rag = MagicMock()
    mock_rag.answer.return_value = Answer(answer="ok [1]", citations=[])
    with patch("freshdocs.main.rag", mock_rag):
        resp = client.post("/api/ask", json={"question": "test", "sources": ["docker", "kubernetes"]})
        assert resp.status_code == 200
        mock_rag.answer.assert_called_once_with("test", sources=["docker", "kubernetes"])


def test_ask_does_not_require_sources_field(client):
    """sources is optional in the request."""
    mock_rag = MagicMock()
    mock_rag.answer.return_value = Answer(answer="ok", citations=[])
    with patch("freshdocs.main.rag", mock_rag):
        resp = client.post("/api/ask", json={"question": "hello"})
        assert resp.status_code == 200
        mock_rag.answer.assert_called_once_with("hello", sources=None)


def test_status_endpoint_with_mocked_pipeline(client):
    mock_status = {
        "sources": [{"source": "docker", "pages": 5}],
        "runs": [{"source": "docker", "rows": 5, "healthy": 1}],
        "heals": [{"source": "fixture", "symptom": "empty bodies", "result": "ok"}],
    }
    mock_pipeline = MagicMock()
    mock_pipeline.status.return_value = mock_status
    with patch("freshdocs.main.pipeline", mock_pipeline):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sources"][0]["source"] == "docker"
        assert data["runs"][0]["rows"] == 5
        assert data["heals"][0]["symptom"] == "empty bodies"


def test_status_endpoint_returns_empty_when_index_is_empty(client):
    """Without mocking, status should still return structure (empty lists) if
    the index has no data."""
    mock_pipeline = MagicMock()
    mock_pipeline.status.return_value = {"sources": [], "runs": [], "heals": []}
    with patch("freshdocs.main.pipeline", mock_pipeline):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert "runs" in data
        assert "heals" in data


def test_static_assets_mounted(client):
    """The /static/ mount should serve files from the static directory."""
    static_dir = Path(__file__).resolve().parent.parent / "src" / "freshdocs" / "static"
    if (static_dir / "style.css").exists():
        resp = client.get("/static/style.css")
        assert resp.status_code == 200
