"""Tests for the Rag (retrieval-augmented generation) module."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from freshdocs.rag import Rag, RagError, COLLECTION_NAME


@pytest.fixture
def rag(tmp_path):
    """Create a Rag instance with a fake API key and ChromaDB in tmp_path."""
    return Rag(data_dir=Path(tmp_path), provider="openai", api_key="sk-test-key")


# --------------------------------------------------------------------------- #
#  Initialization
# --------------------------------------------------------------------------- #

def test_rag_error_without_api_key(tmp_path):
    """Rag should raise RagError when no API key is available."""
    import os
    old_route = os.environ.get("OPENROUTER_API_KEY")
    os.environ["OPENROUTER_API_KEY"] = ""
    try:
        with pytest.raises(RagError):
            Rag(data_dir=Path(tmp_path), provider="openrouter")
    finally:
        if old_route is not None:
            os.environ["OPENROUTER_API_KEY"] = old_route
        else:
            os.environ.pop("OPENROUTER_API_KEY", None)


def test_rag_uses_fixed_collection_name(rag):
    """The ChromaDB collection should use the constant name."""
    # The collection is created in __init__, so accessing it should work
    assert rag.collection.name == COLLECTION_NAME


# --------------------------------------------------------------------------- #
#  embed_texts
# --------------------------------------------------------------------------- #

def test_embed_texts_returns_vectors(rag):
    """embed_texts() should return a list of vectors from the OpenAI API."""
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(embedding=[0.1, 0.2, 0.3]) for _ in range(2)]
    rag.client.embeddings.create = MagicMock(return_value=mock_resp)

    embeddings = rag.embed_texts(["hello", "world"])
    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]
    assert embeddings[1] == [0.1, 0.2, 0.3]


def test_embed_texts_empty_returns_empty(rag):
    """embed_texts() with no texts should return an empty list."""
    assert rag.embed_texts([]) == []


def test_embed_texts_passes_model(rag):
    """embed_texts() should pass the embed_model name to the API."""
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
    rag.client.embeddings.create = MagicMock(return_value=mock_resp)

    rag.embed_texts(["test"])
    _, kwargs = rag.client.embeddings.create.call_args
    assert kwargs["model"] == rag.embed_model


# --------------------------------------------------------------------------- #
#  upsert_chunks / retrieve / delete_page
# --------------------------------------------------------------------------- #

def _mock_openai_for_rag(rag, docker_vector, other_vector):
    """Replace the OpenAI client with a mock that returns fixed embeddings."""
    def fake_create(**kwargs):
        resp = MagicMock()
        resp.data = []
        for t in kwargs["input"]:
            if "docker" in t.lower():
                resp.data.append(MagicMock(embedding=docker_vector))
            else:
                resp.data.append(MagicMock(embedding=other_vector))
        return resp
    rag.client.embeddings.create = MagicMock(side_effect=fake_create)
    return rag


def test_upsert_and_retrieve(rag):
    """Chunks upserted into ChromaDB should be retrievable by similarity."""
    _mock_openai_for_rag(rag, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])

    chunks = [("Docker is a platform for building apps.", "Introduction")]
    n = rag.upsert_chunks(
        url="https://docs.docker.com/get-started",
        chunks=chunks,
        source="docker",
        title="Get Started with Docker",
        scraped_at="2026-08-18",
    )
    assert n == 1

    result = rag.retrieve("docker platform building apps", top_k=1)
    assert len(result["documents"][0]) == 1
    assert result["metadatas"][0][0]["source"] == "docker"


def test_retrieve_with_source_filter(rag):
    """retrieve() should only return chunks from the specified source."""
    _mock_openai_for_rag(rag, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])

    rag.upsert_chunks("https://docs.docker.com/a", [("docker content", "A")],
                      source="docker", title="Docker A", scraped_at="2026-08-18")
    rag.upsert_chunks("https://kubernetes.io/b", [("kubernetes content", "B")],
                      source="kubernetes", title="K8s B", scraped_at="2026-08-18")

    result = rag.retrieve("docker", sources=["docker"], top_k=5)
    metas = result["metadatas"][0]
    assert len(metas) == 1
    assert metas[0]["source"] == "docker"


def test_delete_page_removes_chunks(rag):
    """delete_page() should remove chunks for the given URL."""
    _mock_openai_for_rag(rag, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])

    url = "https://docs.docker.com/page"
    rag.upsert_chunks(url, [("docker content", "Heading")],
                      source="docker", title="Docker", scraped_at="2026-08-18")
    rag.upsert_chunks("https://kubernetes.io/page", [("k8s content", "Heading")],
                      source="kubernetes", title="K8s", scraped_at="2026-08-18")

    rag.delete_page(url)

    result = rag.retrieve("docker", top_k=10)
    sources = {m["source"] for m in result["metadatas"][0]}
    assert "docker" not in sources
    assert "kubernetes" in sources


def test_upsert_zero_chunks_returns_zero(rag):
    """upsert_chunks() with empty chunks should return 0 without calling embed."""
    rag.client.embeddings.create = MagicMock()
    n = rag.upsert_chunks("https://example.com", [],
                          source="x", title="X", scraped_at="2026-08-18")
    assert n == 0
    rag.client.embeddings.create.assert_not_called()


# --------------------------------------------------------------------------- #
#  answer
# --------------------------------------------------------------------------- #

def test_answer_with_citations(rag):
    """answer() should return a response with citations from retrieved chunks."""
    _mock_openai_for_rag(rag, [1.0, 0.0, 0.0], [0.0, 1.0, 0.0])

    rag.upsert_chunks(
        "https://docs.docker.com/get-started",
        [("Docker is a platform for developing, shipping, and running applications.", "Intro")],
        source="docker", title="Get Started with Docker", scraped_at="2026-08-18",
    )

    # Mock chat completion
    mock_msg = MagicMock(content="Docker is a platform [1] for building apps.")
    mock_resp = MagicMock(choices=[MagicMock(message=mock_msg)])
    rag.client.chat.completions.create = MagicMock(return_value=mock_resp)

    answer = rag.answer("What is Docker?")
    assert answer.answer == "Docker is a platform [1] for building apps."
    assert len(answer.citations) == 1
    assert answer.citations[0].source == "docker"
    assert answer.citations[0].url == "https://docs.docker.com/get-started"


def test_answer_no_results(rag):
    """answer() should return a fallback when nothing is retrieved."""
    # Mock embeddings so we don't call the real API
    _mock_openai_for_rag(rag, [0.0, 0.0, 1.0], [0.0, 0.0, 1.0])
    answer = rag.answer("What is quantum computing?")
    assert answer.citations == []
    assert "couldn't find" in answer.answer.lower()
