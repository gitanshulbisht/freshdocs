"""Download already-scraped Bright Data datasets and index them via the pipeline.

Avoids re-triggering slow browser-based scrapes. Uses existing snapshots
that were collected during earlier refresh runs.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from freshdocs.brightdata import BrightDataClient
from freshdocs.pipeline import Pipeline, load_registry
from freshdocs.rag import Rag, RagError
from freshdocs.schemas import DocRow

DATA_DIR = Path("data")
REGISTRY_PATH = Path("collectors/collectors.json")

# Snapshots from earlier Bright Data scraper runs (still available on BD servers)
SNAPSHOTS = {
    "github-actions": "j_mt42iwgv1o08csw6fk",
    "argo-cd": "j_mt42iwhi12wp872q27",
    "aws-eks": "j_mt42o80bez8afll19",
}

client = BrightDataClient()
try:
    rag = Rag(data_dir=DATA_DIR)
    print(f"Rag initialized with model={rag.embed_model}", flush=True)
except RagError as exc:
    print(f"Rag unavailable: {exc}", file=sys.stderr, flush=True)
    rag = None

pipeline = Pipeline(data_dir=DATA_DIR, rag=rag, client=client)
registry = load_registry(REGISTRY_PATH)

for key, snapshot_id in SNAPSHOTS.items():
    source = registry.by_key(key)
    print(f"\n=== {key} ({snapshot_id}) ===", flush=True)

    body = client.dataset(snapshot_id)
    if not isinstance(body, list):
        print(f"  skipping: not ready ({body.get('status', 'unknown')})", flush=True)
        continue
    raw_rows = body
    print(f"  downloaded: {len(raw_rows)} rows", flush=True)

    # Normalize (same logic as collect_source, without triggering a scrape)
    normalized = []
    for raw in raw_rows:
        if not (raw.get("url") or raw.get("product_page_url") or "").strip():
            continue
        doc = DocRow.from_collector(raw)
        normalized.append({
            "url": doc.url,
            "title": doc.title or "",
            "body_text": doc.body or "",
            "last_updated": doc.last_updated,
        })

    print(f"  normalized: {len(normalized)} rows", flush=True)

    # Skip row-count threshold for sources with fewer pages than expected
    source_copy = source.model_copy(update={"expected_urls": 0})

    embed = rag is not None
    outcome = pipeline.refresh_source(source_copy, normalized, embed=embed)
    print(f"  ok={outcome.ok} rows={outcome.rows} embed_count={outcome.embed_count}", flush=True)
    if outcome.failures:
        for f in outcome.failures:
            print(f"  FAIL: {f.symptom}", flush=True)
    else:
        print(f"  indexed successfully", flush=True)

print("\n=== All done! ===", flush=True)
