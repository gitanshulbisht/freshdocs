"""Refresh pipeline: scrape a source, validate, diff, re-embed changes.

Used both by the CLI entrypoint and by CI. The heal-on-failure path is
deliberately a separate explicit step (--heal) so interactive runs stay
visible and demo-able.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .brightdata import BrightDataClient
from .diff import Diff, diff_pages
from .health import HealthCheckFailure, check_scrape
from .index import Index, content_hash, utcnow
from .ingest import page_to_chunks
from .rag import Rag
from .schemas import DocRow, Registry, SourceConfig

log = logging.getLogger(__name__)


@dataclass
class RefreshOutcome:
    source: str
    ok: bool
    rows: int
    diff: Optional[Diff] = None
    failures: list[HealthCheckFailure] = field(default_factory=list)
    notes: str = ""


def load_registry(path: Path) -> Registry:
    with open(path, encoding="utf-8") as handle:
        return Registry.model_validate(json.load(handle))


def collector_ids_from_env() -> dict[str, str]:
    raw = os.environ.get("BRIGHT_DATA_COLLECTOR_IDS", "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("BRIGHT_DATA_COLLECTOR_IDS must be a JSON map, e.g. {\"docker\": \"c_xxx\"}") from exc


def effective_collector_id(source: SourceConfig, env_ids: dict[str, str]) -> str:
    return env_ids.get(source.key) or source.collector_id or ""


def collect_source(client: BrightDataClient, source: SourceConfig) -> list[dict[str, Any]]:
    collector_id = effective_collector_id(source, collector_ids_from_env())
    if not collector_id:
        raise RuntimeError(f"no collector id for source '{source.key}' — create it with bdata scraper create")
    return client.collect(collector_id, [{"url": source.sitemap_url}])


class Pipeline:
    def __init__(self, data_dir: Path, rag: Optional[Rag] = None,
                 client: Optional[BrightDataClient] = None) -> None:
        self.data_dir = data_dir
        self.outputs_dir = data_dir / "outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.index = Index(data_dir / "index.sqlite")
        self.rag = rag
        self._client = client

    @property
    def client(self) -> BrightDataClient:
        """Bright Data client, created lazily so the app can start (and serve
        status/UI) before credentials are configured."""
        if self._client is None:
            self._client = BrightDataClient()
        return self._client

    def refresh_source(self, source: SourceConfig, rows: list[dict[str, Any]],
                       embed: bool = True, dry_run: bool = False) -> RefreshOutcome:
        """Full refresh for one source: validate, diff, store, (re-)embed."""
        report = check_scrape(source, rows)
        if report.failures:
            self.index.start_run(source.key)
            outcome = RefreshOutcome(source=source.key, ok=False, rows=len(rows),
                                     failures=report.failures,
                                     notes="health check failed; run --heal with the symptom text")
            return outcome

        scraped_at = utcnow()

        # Normalize rows once so hash/embed agree.
        normalized: dict[str, DocRow] = {}
        for raw in rows:
            row = DocRow.from_collector(raw)
            if row.url:
                normalized[row.url] = row

        old_hashes = self.index.page_hashes(source.key)
        new_hashes = {url: content_hash(row.body) for url, row in normalized.items()}
        page_diff = diff_pages(old_hashes, new_hashes)
        log.info("%s: %s", source.key, page_diff.summary())

        if dry_run:
            return RefreshOutcome(source=source.key, ok=True, rows=len(rows), diff=page_diff,
                                  notes="dry run — nothing written")

        run_id = self.index.start_run(source.key)

        embed_count = 0
        chunk_counts: dict[str, int] = {}
        if self.rag and embed:
            for url in page_diff.reembed:
                row = normalized.get(url)
                if not row:
                    continue
                chunks = page_to_chunks(row.body)
                chunk_counts[url] = len(chunks)
                embed_count += self.rag.upsert_chunks(
                    url, [(c.text, c.heading) for c in chunks],
                    source=source.key, title=row.title, scraped_at=scraped_at,
                )
            for url in page_diff.removed:
                self.rag.delete_page(url)

        for url, row in normalized.items():
            self.index.upsert_page(
                url=url, source=source.key, title=row.title,
                body_hash=content_hash(row.body),
                chunks=chunk_counts.get(url, 0), scraped_at=scraped_at,
            )
        self.index.remove_pages(page_diff.removed)

        # Persist example output for the repo.
        with open(self.outputs_dir / f"{source.key}.json", "w", encoding="utf-8") as handle:
            json.dump([r for r in rows if (r.get("url") or "").strip()], handle,
                      indent=2, ensure_ascii=False)

        notes = page_diff.summary() + (f" embedded={embed_count}" if self.rag else "")
        self.index.finish_run(run_id, rows=len(rows), added=len(page_diff.added),
                              changed=len(page_diff.changed), removed=len(page_diff.removed),
                              healthy=True, notes=notes)
        return RefreshOutcome(source=source.key, ok=True, rows=len(rows), diff=page_diff, notes=notes)

    def refresh_all(self, registry: Registry, embed: bool = True,
                    dry_run: bool = False) -> dict[str, RefreshOutcome]:
        outcomes: dict[str, RefreshOutcome] = {}
        for source in registry.sources:
            if not source.sitemap_url.startswith("http"):
                continue
            log.info("refreshing %s", source.key)
            rows = collect_source(self.client, source)
            outcomes[source.key] = self.refresh_source(source, rows, embed=embed, dry_run=dry_run)
        return outcomes

    def status(self) -> dict[str, Any]:
        return {
            "sources": self.index.source_status(),
            "runs": self.index.recent_runs(),
            "heals": self.index.recent_heals(),
        }
