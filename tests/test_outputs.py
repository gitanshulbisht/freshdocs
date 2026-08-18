"""Tests for committed example outputs and collector config consistency."""

import json
from pathlib import Path

from freshdocs.schemas import Registry

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "collectors" / "collectors.json"
OUTPUTS_DIR = ROOT / "data" / "outputs"


def load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_registry_is_valid_json():
    data = load_registry()
    assert "sources" in data
    source_keys = {s["key"] for s in data["sources"]}
    expected = {"docker", "kubernetes", "aws-eks", "argo-cd", "github-actions", "langchain", "fixture"}
    assert source_keys == expected


def test_registry_sources_have_required_fields():
    data = load_registry()
    for source in data["sources"]:
        assert "key" in source
        assert "category" in source
        assert "name" in source
        assert "sitemap_url" in source
        assert source["sitemap_url"].startswith("http"), f"sitemap_url missing http for {source['key']}"
        assert "expected_urls" in source
        assert isinstance(source["expected_urls"], int)
        assert source["expected_urls"] > 0
        assert "create_prompt" in source
        assert source["create_prompt"]


def test_registry_source_keys_match_categories():
    data = load_registry()
    for source in data["sources"]:
        # Verify SourceConfig pydantic model accepts the registry entry
        config = Registry.model_validate(data)
        src = config.by_key(source["key"])
        assert src.key == source["key"]
        assert src.category == source["category"]
        assert src.name == source["name"]


def test_fixture_collector_id_is_set():
    data = load_registry()
    fixture = [s for s in data["sources"] if s["key"] == "fixture"][0]
    assert fixture["collector_id"], "fixture source must have a collector_id"


def test_docker_collector_id_is_set():
    data = load_registry()
    docker = [s for s in data["sources"] if s["key"] == "docker"][0]
    assert docker["collector_id"], "docker source must have a collector_id"


def test_fixture_example_output_matches_sitemap():
    """The committed data/outputs/fixture.json should have rows for every URL
    in the demo fixture sitemap."""
    sitemap_path = ROOT / "demo" / "fixture-site" / "sitemap.xml"
    output_path = OUTPUTS_DIR / "fixture.json"

    assert output_path.exists(), "fixture.json example output must be committed"
    rows = json.loads(output_path.read_text())
    assert isinstance(rows, list)
    assert len(rows) >= 4, f"expected >=4 fixture rows, got {len(rows)}"

    # Every row must have url, title, body_text populated
    for row in rows:
        assert row.get("url", "").strip(), f"row missing url: {row}"
        assert row.get("title", "").strip(), f"row missing title: {row}"
        assert row.get("body_text", "").strip(), f"row missing body_text: {row}"

    # Extract URLs from sitemap and verify they match the output
    sitemap = sitemap_path.read_text()
    sitemap_urls = set()
    for line in sitemap.splitlines():
        if "<loc>" in line and "</loc>" in line:
            url = line.split("<loc>")[1].split("</loc>")[0].strip()
            sitemap_urls.add(url)

    output_urls = {r["url"] for r in rows}
    assert sitemap_urls == output_urls, (
        f"output URLs {output_urls} != sitemap URLs {sitemap_urls}"
    )


def test_collectors_json_output_files_exist():
    """The collectors/ directory has JSON files from bdata scraper create for
    docker and fixture — these should have valid collector IDs."""
    for name in ("docker.json", "fixture.json"):
        path = ROOT / "collectors" / name
        assert path.exists(), f"{name} should exist with create output"
        data = json.loads(path.read_text())
        assert data.get("status") == "done"
        assert data.get("collector_id", "").startswith("c_"), \
            f"{name} collector_id should start with c_"


def test_break_restore_scripts_are_in_sync():
    """The break and restore scripts should have inverse tag transformations."""
    repo = ROOT / "scripts"
    break_script = (repo / "break_fixture.sh").read_text()
    restore_script = (repo / "restore_fixture.sh").read_text()

    # Every replacement in break should have an inverse in restore
    break_replacements = [
        ('<article>', '<div class="content-v2">'),
        ('</article>', '</div>'),
        ('<h1', '<h3 class="page-heading"'),
        ('</h1>', '</h3>'),
        ('<p>', '<span class="article-body">'),
        ('</p>', '</span>'),
    ]
    restore_replacements = [
        ('<div class="content-v2">', '<article>'),
        ('</div>', '</article>'),
        ('<h3 class="page-heading">', '<h1>'),
        ('</h3>', '</h1>'),
        ('<span class="article-body">', '<p>'),
        ('</span>', '</p>'),
    ]

    for old, new in break_replacements:
        # The break script must contain the replacement
        assert old in break_script and new in break_script, \
            f"break script missing: {old} → {new}"

    for old, new in restore_replacements:
        assert old in restore_script and new in restore_script, \
            f"restore script missing: {old} → {new}"
