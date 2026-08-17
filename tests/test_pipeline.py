"""End-to-end pipeline test with a fake Bright Data client (no credentials)."""

from pathlib import Path

from freshdocs.pipeline import Pipeline, RefreshOutcome
from freshdocs.schemas import SourceConfig


class FakeClient:
    def __init__(self) -> None:
        self.rows: list[list[dict]] = []

    def collect(self, collector_id: str, inputs: list[dict]):
        return self.rows.pop(0)


def make_source() -> SourceConfig:
    return SourceConfig(
        key="docker", category="DevOps", name="Docker Docs",
        sitemap_url="https://docs.docker.com/sitemap.xml",
        collector_id="c_fake", expected_urls=2,
    )


def rows_v1() -> list[dict]:
    return [
        {"url": "https://docs.docker.com/a", "title": "A",
         "body_text": "<html><h1>Intro</h1><p>Page A body.</p></html>"},
        {"url": "https://docs.docker.com/b", "title": "B",
         "body_text": "<html><h1>Intro</h1><p>Page B body.</p></html>"},
    ]


def test_full_lifecycle(tmp_path: Path):
    client = FakeClient()
    pipeline = Pipeline(data_dir=tmp_path, client=client, rag=None)

    # First refresh: everything is new.
    client.rows = [rows_v1()]
    outcome = pipeline.refresh_source(make_source(), client.rows[0], embed=False)
    assert outcome.ok
    assert outcome.diff is not None
    assert set(outcome.diff.added) == {"https://docs.docker.com/a", "https://docs.docker.com/b"}
    assert pipeline.index.page_count("docker") == 2

    # Second refresh: b changed, a unchanged, c added (d removed).
    client.rows = [[
        {"url": "https://docs.docker.com/a", "title": "A",
         "body_text": "<html><h1>Intro</h1><p>Page A body.</p></html>"},
        {"url": "https://docs.docker.com/b", "title": "B",
         "body_text": "<html><h1>Intro</h1><p>Page B body CHANGED.</p></html>"},
        {"url": "https://docs.docker.com/c", "title": "C",
         "body_text": "<html><h1>Intro</h1><p>Page C body.</p></html>"},
    ]]
    outcome = pipeline.refresh_source(make_source(), client.rows[0], embed=False)
    assert outcome.ok
    assert outcome.diff.added == ["https://docs.docker.com/c"]
    assert outcome.diff.changed == ["https://docs.docker.com/b"]
    assert outcome.diff.removed == []  # d was never in the index
    assert outcome.diff.unchanged == 1

    # Status shows the latest state.
    status = pipeline.status()
    assert status["sources"][0]["source"] == "docker"
    assert status["sources"][0]["pages"] == 3

    # Example output persisted.
    output = tmp_path / "outputs" / "docker.json"
    assert output.exists()


def test_unhealthy_scrape_is_rejected_without_index_mutation(tmp_path: Path):
    client = FakeClient()
    pipeline = Pipeline(data_dir=tmp_path, client=client, rag=None)

    client.rows = [[
        {"url": f"https://docs.docker.com/{i}", "title": "", "body_text": ""}
        for i in range(2)
    ]]
    outcome = pipeline.refresh_source(make_source(), client.rows[0], embed=False)
    assert not outcome.ok
    assert outcome.failures
    assert pipeline.index.page_count("docker") == 0
