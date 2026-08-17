"""Typed models for scraped docs rows, source config, and pipeline health."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DocRow(BaseModel):
    """One row returned by a Bright Data Sitemap collector.

    Field names follow the collector output schema we request at creation time.
    Values are normalized here so downstream code never depends on exact naming.
    """

    url: str = ""
    title: str = ""
    body: str = ""
    last_updated: Optional[str] = None

    @classmethod
    def from_collector(cls, raw: dict[str, Any]) -> "DocRow":
        """Normalize a raw collector row (any of the common field spellings)."""
        def first(*keys: str) -> str:
            for key in keys:
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return ""

        url = first("url", "canonical_url", "canonicalURL", "page_url", "pageUrl")
        if not url and isinstance(raw.get("input"), dict):
            url = str(raw["input"].get("url") or "").strip()

        body = first("body_text", "bodyText", "body", "content", "text", "main_text", "article")
        title = first("title", "page_title", "pageTitle", "name", "heading")

        updated = None
        for key in ("last_updated", "lastUpdated", "updated_at", "last_modified", "modified"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                updated = value.strip()
                break

        return cls(url=url, title=title, body=body, last_updated=updated)


class SourceConfig(BaseModel):
    """One docs source from collectors/collectors.json."""

    key: str
    category: str
    name: str
    sitemap_url: str
    collector_id: str = ""
    expected_urls: int = 0
    create_prompt: str = ""


class Registry(BaseModel):
    """The whole collectors.json registry."""

    sources: list[SourceConfig]

    def by_key(self, key: str) -> SourceConfig:
        for source in self.sources:
            if source.key == key:
                return source
        raise KeyError(key)


class HealthCheckFailure(BaseModel):
    """Raised when a fresh scrape looks broken — carries the exact symptom text
    we feed to `bdata scraper heal`."""

    source: str
    collector_id: str
    symptom: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    source: str
    ok: bool
    rows: int
    empty_body_rate: float
    failures: list[HealthCheckFailure] = Field(default_factory=list)


class Citation(BaseModel):
    index: int
    title: str
    url: str
    source: str
    snippet: str


class Answer(BaseModel):
    answer: str
    citations: list[Citation]


class SourceStatus(BaseModel):
    key: str
    name: str
    category: str
    pages: int
    last_refresh: Optional[str] = None
    healthy: bool = True
