#!/usr/bin/env python
"""Re-index already-scraped Bright Data datasets with batched embeddings.

Downloads existing snapshot datasets via GET /dca/dataset and re-indexes them
through the pipeline with corrected field-name normalization.  Uses paragraph-based
chunking (not heading-split) to avoid 300+ tiny chunks per page.  All chunks are
batch-embedded (BATCH_SIZE per API call) instead of one call per page.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from freshdocs.brightdata import BrightDataClient
from freshdocs.rag import Rag, RagError
from freshdocs.schemas import DocRow
from freshdocs.ingest import Chunk
from freshdocs.pipeline import Pipeline, load_registry
from freshdocs.index import content_hash, utcnow

DATA_DIR = Path("data")
REGISTRY_PATH = Path("collectors/collectors.json")
BATCH_SIZE = 50
CHUNK_CHARS = 8000

SNAPSHOTS = {
    "github-actions": "j_mt42iwgv1o08csw6fk",
    "argo-cd": "j_mt42iwhi12wp872q27",
    "aws-eks": "j_mt42o80bez8afll19",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NEWLINES_RE = re.compile(r"\n{3,}")


def simple_chunk(text: str, max_chars: int = CHUNK_CHARS) -> list[Chunk]:
    """Paragraph-based chunking — avoids heading-split explosion."""
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text).strip()
    if not text:
        return []
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(Chunk(text=current.strip(), heading=""))
            current = para
        else:
            current += "\n\n" + para if current else para
    if current.strip():
        chunks.append(Chunk(text=current.strip(), heading=""))
    return chunks


def main() -> None:
    client = BrightDataClient()

    try:
        rag = Rag(data_dir=DATA_DIR)
        print("Rag initialized", flush=True)
    except RagError as exc:
        print(f"Rag unavailable: {exc}", file=sys.stderr, flush=True)
        rag = None

    pipeline = Pipeline(data_dir=DATA_DIR, rag=rag, client=client)
    registry = load_registry(REGISTRY_PATH)
    scraped_at = utcnow()

    total_pages = 0
    total_chunks = 0
    embed_count = 0
    t0 = time.time()

    for key, snapshot_id in SNAPSHOTS.items():
        source = registry.by_key(key)
        print(f"=== {key} ({snapshot_id}) ===", flush=True)

        # --- Clean up old embeddings ---
        if rag:
            try:
                pipeline.rag.collection.delete(where={"source": key})
                print(f"  cleared old embeddings", flush=True)
            except Exception as exc:
                print(f"  warn: cleanup: {exc}", flush=True)
            old_hashes = pipeline.index.page_hashes(key)
            if old_hashes:
                pipeline.index.remove_pages(list(old_hashes.keys()))
                print(f"  removed {len(old_hashes)} old SQLite rows", flush=True)

        # --- Download existing dataset (no new scrape) ---
        body = client.dataset(snapshot_id)
        if not isinstance(body, list):
            print(f"  not ready: {body.get('status', 'unknown')}", flush=True)
            continue
        print(f"  downloaded: {len(body)} rows", flush=True)

        # --- Normalize using fixed DocRow.from_collector ---
        docs = []
        for raw in body:
            if not (raw.get("url") or raw.get("product_page_url") or "").strip():
                continue
            doc = DocRow.from_collector(raw)
            if doc.url:
                docs.append(doc)
        empty_body = sum(1 for d in docs if not d.body.strip())
        empty_title = sum(1 for d in docs if not d.title.strip())
        print(f"  normalized: {len(docs)} rows (empty_body={empty_body}, empty_title={empty_title})", flush=True)
        total_pages += len(docs)

        # --- Start SQLite run ---
        run_id = pipeline.index.start_run(key)

        # --- Chunk pages and collect all chunks ---
        all_chunks: list[tuple] = []  # (url, source_key, title, heading, text, chunk_idx, scraped_at)
        for doc in docs:
            chunks = simple_chunk(doc.body)
            for idx, c in enumerate(chunks):
                all_chunks.append((doc.url, key, doc.title, c.heading, c.text, idx, scraped_at))

        print(f"  chunks: {len(all_chunks)} ({len(all_chunks)/max(len(docs),1):.1f}/page)", flush=True)
        total_chunks += len(all_chunks)

        # --- Store page metadata in SQLite ---
        for doc in docs:
            pipeline.index.upsert_page(
                url=doc.url, source=key, title=doc.title,
                body_hash=content_hash(doc.body),
                chunks=simple_chunk_count(doc.body),
                scraped_at=scraped_at,
            )

        # --- Batch-embed and store in ChromaDB ---
        if rag and all_chunks:
            for batch_start in range(0, len(all_chunks), BATCH_SIZE):
                batch = all_chunks[batch_start:batch_start + BATCH_SIZE]
                texts = [c[4] for c in batch]
                embeddings = rag.embed_texts(texts)
                ids = [f"{c[0]}#{c[5]}" for c in batch]
                metadatas = [
                    {"url": c[0], "source": c[1], "title": c[2],
                     "heading": c[3], "scraped_at": c[6]}
                    for c in batch
                ]
                rag.collection.upsert(
                    ids=ids, embeddings=embeddings,
                    documents=texts, metadatas=metadatas,
                )
                embed_count += len(batch)
                done = min(batch_start + BATCH_SIZE, len(all_chunks))
                print(f"  {key}: embedded {done}/{len(all_chunks)} ({time.time() - t0:.1f}s)", flush=True)

        notes = f"embedded={embed_count}" if rag else "no embedding (Rag unavailable)"
        pipeline.index.finish_run(
            run_id, rows=len(docs), added=len(docs),
            changed=0, removed=0, healthy=True, notes=notes,
        )
        print(f"  done: {len(docs)} pages, {len(all_chunks)} chunks", flush=True)

    print(f"\nSummary: {total_pages} pages, {total_chunks} chunks, "
          f"{embed_count} embeddings in {time.time() - t0:.1f}s", flush=True)


def simple_chunk_count(text: str) -> int:
    return len(simple_chunk(text))


if __name__ == "__main__":
    main()
