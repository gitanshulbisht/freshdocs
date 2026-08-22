#!/usr/bin/env python
"""Background monitor: poll Bright Data scrapers, re-index when ready.

Polls Docker and Kubernetes snapshots every 5 minutes. When a snapshot
becomes ready (returns a JSON array), re-indexes it via index_ready.py.
Once Kubernetes completes, triggers the LangChain scraper (sequential).
"""
import os, sys, time, json, subprocess
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from freshdocs.brightdata import BrightDataClient
from freshdocs.pipeline import load_registry

client = BrightDataClient()
registry = load_registry(Path("collectors/collectors.json"))

# snapshots to monitor: snapshot_id -> source_key
MONITOR = {
    "j_mt45amdyy6o9v8dlh": "docker",
    "j_mt45yspu23s03gya2v": "kubernetes",
}

POLL_INTERVAL = 300  # 5 minutes


def poll_snapshots():
    """Return dict: source_key -> ('ready', row_count) | ('collecting', 0) | (error, 0)."""
    out = {}
    for snapshot_id, key in MONITOR.items():
        body = client.dataset(snapshot_id)
        if isinstance(body, list):
            out[key] = ("ready", len(body))
        elif isinstance(body, dict) and body.get("status"):
            out[key] = (body["status"], 0)
        else:
            out[key] = ("unknown", 0)
    return out


def reindex(sources: list[str]):
    """Run the batch re-indexing script for the specified sources."""
    result = subprocess.run(
        [sys.executable, "scripts/index_ready.py", "--sources"] + sources,
        capture_output=True, text=True, timeout=1800,
    )
    print(f"  re-index exit={result.returncode}", flush=True)
    print(f"  stdout (last 800 chars): {result.stdout[-800:]}", flush=True)
    if result.returncode != 0:
        print(f"  stderr: {result.stderr[-800:]}", flush=True)


def trigger_langchain():
    """Trigger the LangChain scraper (called once Kubernetes finishes)."""
    source = registry.by_key("langchain")
    snapshot_id = client.trigger(source.collector_id, [{"url": source.sitemap_url}])
    print(f"  LangChain scraper triggered: snapshot={snapshot_id} (~4.3 hrs)", flush=True)
    MONITOR[snapshot_id] = "langchain"


def main():
    print(f"Monitoring {len(MONITOR)} scrapers: {list(MONITOR.values())}", flush=True)
    langchain_triggered = False
    reindexed = set()

    while True:
        try:
            status = poll_snapshots()
            ready = []
            for key, (state, rows) in status.items():
                tag = f"[{time.strftime('%H:%M:%S')}]"
                if state == "ready":
                    print(f"{tag} {key}: READY ({rows} rows)", flush=True)
                    ready.append(key)
                else:
                    print(f"{tag} {key}: {state}", flush=True)

            # Re-index newly-ready sources
            newly_ready = [k for k in ready if k not in reindexed]
            if newly_ready:
                print(f"Re-indexing {newly_ready}...", flush=True)
                reindex(newly_ready)
                reindexed.update(newly_ready)

            # Trigger LangChain once Kubernetes is done
            if "kubernetes" in reindexed and not langchain_triggered:
                print("Kubernetes complete — triggering LangChain...", flush=True)
                trigger_langchain()
                langchain_triggered = True

            if all(k in reindexed for k in MONITOR.values()) and langchain_triggered:
                print("All sources indexed and LangChain triggered. Stopping.", flush=True)
                return

        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] monitor error: {exc}", flush=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
