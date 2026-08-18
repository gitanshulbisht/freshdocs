"""Tests for the SQLite Index (pages, runs, heal events)."""

import sqlite3
from pathlib import Path

import pytest

from freshdocs.index import Index, content_hash, utcnow


@pytest.fixture
def idx(tmp_path: Path) -> Index:
    return Index(tmp_path / "test.db")


def test_content_hash_is_deterministic():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


def test_utcnow_format():
    ts = utcnow()
    assert "T" in ts  # ISO format
    assert ts.endswith("+00:00") or ts.endswith("Z") or "+" in ts


def test_upsert_and_page_count(idx: Index):
    h = content_hash("body1")
    idx.upsert_page("https://x.com/1", "docker", "Title 1", h, chunks=3, scraped_at=utcnow())
    assert idx.page_count("docker") == 1

    rows = idx.page_hashes("docker")
    assert rows["https://x.com/1"] == h


def test_upsert_overwrites_existing(idx: Index):
    ts = utcnow()
    idx.upsert_page("https://x.com/1", "docker", "Title 1", content_hash("body1"), 3, ts)
    idx.upsert_page("https://x.com/1", "docker", "Title 1 Updated", content_hash("body2"), 5, ts)
    assert idx.page_count("docker") == 1
    rows = idx.page_hashes("docker")
    assert rows["https://x.com/1"] == content_hash("body2")


def test_remove_pages(idx: Index):
    ts = utcnow()
    for i in range(3):
        idx.upsert_page(f"https://x.com/{i}", "docker", f"T{i}", content_hash(f"b{i}"), 1, ts)
    assert idx.page_count("docker") == 3

    idx.remove_pages(["https://x.com/0", "https://x.com/2"])
    assert idx.page_count("docker") == 1
    rows = idx.page_hashes("docker")
    assert list(rows) == ["https://x.com/1"]


def test_remove_pages_empty_noop(idx: Index):
    ts = utcnow()
    idx.upsert_page("https://x.com/1", "docker", "T", content_hash("b"), 1, ts)
    idx.remove_pages([])  # should not raise
    assert idx.page_count("docker") == 1


def test_source_status(idx: Index):
    ts = utcnow()
    idx.upsert_page("https://x.com/1", "docker", "T1", content_hash("b1"), 2, ts)
    idx.upsert_page("https://x.com/2", "docker", "T2", content_hash("b2"), 3, ts)
    idx.upsert_page("https://y.com/1", "kubernetes", "T3", content_hash("b3"), 1, ts)

    status = idx.source_status()
    assert len(status) == 2
    docker_row = [s for s in status if s["source"] == "docker"][0]
    assert docker_row["pages"] == 2


def test_runs(idx: Index):
    run_id = idx.start_run("docker")
    idx.finish_run(run_id, rows=10, added=5, changed=3, removed=2, healthy=True, notes="ok")

    runs = idx.recent_runs()
    assert len(runs) == 1
    assert runs[0]["source"] == "docker"
    assert runs[0]["rows"] == 10
    assert runs[0]["added"] == 5
    assert runs[0]["changed"] == 3
    assert runs[0]["removed"] == 2
    assert runs[0]["healthy"] == 1
    assert runs[0]["finished_at"] is not None


def test_heal_events(idx: Index):
    idx.record_heal("fixture", "c_test", "empty body_text", result="ok")

    heals = idx.recent_heals()
    assert len(heals) == 1
    assert heals[0]["source"] == "fixture"
    assert heals[0]["collector_id"] == "c_test"
    assert heals[0]["symptom"] == "empty body_text"
    assert heals[0]["result"] == "ok"


def test_run_id_is_returned_from_start(idx: Index):
    rid = idx.start_run("docker")
    assert isinstance(rid, int)
    assert rid > 0
