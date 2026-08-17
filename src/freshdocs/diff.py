"""Content-hash diff between the old index and a fresh scrape."""

from __future__ import annotations

from dataclasses import dataclass, field

from .index import content_hash


@dataclass
class Diff:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0

    @property
    def reembed(self) -> list[str]:
        return self.added + self.changed

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.changed) + len(self.removed)

    def summary(self) -> str:
        return (
            f"added={len(self.added)} changed={len(self.changed)} "
            f"removed={len(self.removed)} unchanged={self.unchanged}"
        )


def diff_pages(old: dict[str, str], fresh: dict[str, str]) -> Diff:
    """Compare old {url: hash} with fresh {url: hash}."""
    result = Diff()
    old_urls = set(old)
    fresh_urls = set(fresh)

    for url in fresh_urls - old_urls:
        result.added.append(url)
    for url in old_urls - fresh_urls:
        result.removed.append(url)
    for url in old_urls & fresh_urls:
        if old[url] != fresh[url]:
            result.changed.append(url)
        else:
            result.unchanged += 1

    result.added.sort()
    result.changed.sort()
    result.removed.sort()
    return result


def fresh_hashes(rows: list[dict]) -> dict[str, str]:
    """Build {url: hash} from raw collector rows (url + body_text fields)."""
    hashes: dict[str, str] = {}
    for row in rows:
        url = (row.get("url") or "").strip()
        body = (row.get("body_text") or row.get("body") or "").strip()
        if not url:
            continue
        hashes[url] = content_hash(body)
    return hashes
