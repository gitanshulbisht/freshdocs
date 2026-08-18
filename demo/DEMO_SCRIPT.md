# FreshDocs Demo Storyboard (3 minutes)

## Setup (pre-demo, 1 min)
```bash
# One terminal: start the API + web UI
bash scripts/run_refresh.sh --source fixture   # scrape + index the fixture docs
uvicorn src.freshdocs.main:app --reload         # opens http://localhost:8000
```

**Prereq:** `.env` has `BRIGHT_DATA_API_TOKEN` + `BRIGHT_DATA_COLLECTOR_IDS` (with the fixture collector ID).

---

## Demo Flow

### 1. Healthy chatbot answers from fixture docs (30s)
Open http://localhost:8000 in a browser.

- Ask: **"How do I install AcmeDB with Docker?"**
- Bot answers from the indexed fixture docs, citing the installation page URL.
- Source chip "fixture" shows a green freshness badge: `5 pages · 2026-08-11`.

### 2. Simulate a docs site redesign (30s)
In another terminal, "break" the fixture site:

```bash
bash scripts/break_fixture.sh
cd demo/fixture-site && git add -A && git commit -m "redesign: rename CSS classes" && git push
```

This renames CSS classes (`.content`→`.content-v2`, `.body-text`→`.article-body`, etc.) and downgrades `<h1>`→`<h2>`. The Bright Data scraper's selectors now miss the body text.

### 3. Run refresh → health check catches it (30s)
```bash
bash scripts/run_refresh.sh --source fixture
```

Output:
```
fixture: HEALTH FAILURE — 20% of rows have an empty body_text field — the content
extraction is broken, probably because the page layout changed.
```

The bot now can't answer the same question — it says "I couldn't find anything about that."

### 4. Self-heal → recover (30s)
```bash
python -m freshdocs.cli heal c_msya0kbloj7pqkjkj "body_text extraction broken after site redesign — CSS classes renamed, h1 downgraded to h2"
```

The Bright Data CLI's AI proposes a fix (updated selectors), we approve it (same Collector ID), then:

```bash
bash scripts/run_refresh.sh --source fixture   # re-scrape + re-embed
```

Health check passes, rows recovered, and the bot answers the original question again with citations.

---

## CI equivalent
In `.github/workflows/refresh.yml`, the nightly cron runs `scripts/run_refresh.sh` with `--heal`, so the break→heal→recover loop runs automatically when real docs sites change.

## Key message for judges
- **Problem:** docs go stale daily; RAG pipelines are static.
- **Solution:** Bright Data Sitemap collectors on a schedule + content-hash diff → re-embed only what changed.
- **Differentiator:** health checks detect breakage → `bdata scraper heal + approve` on the same Collector ID → zero downstream changes, bot recovers instantly.
