"""Embedding + vector store + retrieval + answer generation."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from openai import OpenAI

from .schemas import Answer, Citation

log = logging.getLogger(__name__)

COLLECTION_NAME = "freshdocs"
TOP_K = 6


class RagError(RuntimeError):
    pass


class Rag:
    def __init__(self, data_dir: Path, api_key: Optional[str] = None,
                 embed_model: Optional[str] = None, answer_model: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise RagError("OPENAI_API_KEY is not set")

        self.embed_model = embed_model or os.environ.get("FRESHDOCS_EMBED_MODEL", "text-embedding-3-small")
        self.answer_model = answer_model or os.environ.get("FRESHDOCS_ANSWER_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key)

        chroma_dir = data_dir / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self.chroma = chromadb.PersistentClient(path=str(chroma_dir))
        self.collection = self.chroma.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )

    # ---- write path ------------------------------------------------------

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.embed_model, input=texts)
        return [item.embedding for item in response.data]

    def upsert_chunks(self, url: str, chunks: list[tuple[str, str]],
                      source: str, title: str, scraped_at: str) -> int:
        """Insert (or replace) all chunks of one page. Returns chunk count."""
        if not chunks:
            return 0
        ids = [f"{url}#{i}" for i in range(len(chunks))]
        metadatas = [
            {"url": url, "source": source, "title": title, "heading": heading,
             "scraped_at": scraped_at}
            for _, heading in chunks
        ]
        embeddings = self.embed_texts([text for text, _ in chunks])
        self.collection.upsert(ids=ids, embeddings=embeddings, documents=[t for t, _ in chunks],
                               metadatas=metadatas)
        return len(chunks)

    def delete_page(self, url: str) -> None:
        self.collection.delete(where={"url": url})

    # ---- read path -------------------------------------------------------

    def retrieve(self, query: str, sources: Optional[list[str]] = None, top_k: int = TOP_K):
        query_embedding = self.embed_texts([query])[0]
        where = None
        if sources:
            where = {"source": {"$in": sources}}
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

    def answer(self, query: str, sources: Optional[list[str]] = None) -> Answer:
        result = self.retrieve(query, sources=sources)
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]

        if not documents:
            return Answer(
                answer="I couldn't find anything about that in the indexed docs.",
                citations=[],
            )

        context_blocks = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas), start=1):
            context_blocks.append(
                f"[{i}] source={meta['source']} title={meta.get('title', '')} url={meta['url']}\n{doc}"
            )
        context = "\n\n".join(context_blocks)

        system = (
            "You are FreshDocs, an assistant that answers questions strictly from the provided "
            "documentation excerpts. Rules:\n"
            "- Answer only using the excerpts below; never use outside knowledge.\n"
            "- If the excerpts do not contain the answer, say so explicitly.\n"
            "- Cite the excerpts you use with their bracketed numbers, e.g. [1] or [1][3].\n"
            "- Keep the answer concise and technical.\n"
            "- Never invent URLs, flags, version numbers, or API names."
        )
        completion = self.client.chat.completions.create(
            model=self.answer_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Documentation excerpts:\n\n{context}\n\nQuestion: {query}"},
            ],
            temperature=0.2,
        )
        text = completion.choices[0].message.content or ""

        used: dict[int, Citation] = {}
        for i, meta in enumerate(metadatas, start=1):
            if f"[{i}]" in text:
                used[i] = Citation(
                    index=i,
                    title=meta.get("title", ""),
                    url=meta["url"],
                    source=meta["source"],
                    snippet=(documents[i - 1] or "")[:280],
                )
        # Preserve citation order as first-used.
        ordered = [used[i] for i in sorted(used)]

        return Answer(answer=text, citations=ordered)
