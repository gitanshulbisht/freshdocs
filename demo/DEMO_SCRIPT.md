# FreshDocs — 4-minute demo storyboard

**Goal:** show the full loop judges are asked to look for: CLI create → run → real downstream (chatbot) → site change breaks the scraper → health check notices → `bdata scraper heal` → approve → recover. Same Collector ID throughout.

## 0: Setup (before recording)

- Fixture site deployed to GitHub Pages, sitemap URL set in `collectors/collectors.json`.
- Fixture collector created and its ID pinned in `CLAUDE.md`.
- Full ingest run: `bash scripts/run_refresh.sh` (Docker + fixture minimum).
- App running: `uvicorn src.freshdocs.main:app`.

## 1: The problem (30s)

- "Devs live in docs. Docs change weekly. RAG pipelines don't."
- Show Docker's sitemap lastmod dates from this week vs a stale chatbot answer.

## 2: Build the scraper from the terminal (45s)

- `npx -p @brightdata/cli bdata scraper create https://docs.docker.com/sitemap.xml "<prompt>"`
- Scroll the AI-generated schema; approve. Note: "5–15 min generation — I pre-built five of these; IDs are pinned in CLAUDE.md."
- `bdata scraper run c_docker https://docs.docker.com/sitemap.xml --pretty` → show rows.

## 3: The product (60s)

- Open http://localhost:8000. Ask: *"How do I persist data between container restarts in Docker?"* → answer + citations.
- Show source chips: filter to just Kubernetes, ask a K8s question.
- Show right rail: per-source page counts, freshness, run history.

## 4: The scrape pipeline in CI (30s)

- Open `.github/workflows/refresh.yml`: nightly cron → `POST /dca/trigger` → poll `/dca/dataset` → health check → diff → re-embed only changed pages.
- Show a run's log line: `docker: added=0 changed=3 removed=0 unchanged=997`.

## 5: Break it (45s)

- `bash scripts/break_fixture.sh` → commit → push to the fixture repo (classes renamed, h1→h2 — the classic "site changed a class name" break).
- Run `bash scripts/run_refresh.sh --source fixture` → health check fails:
  `HEALTH FAILURE [fixture] -> 100% of rows have an empty body_text field...`

## 6: Heal it (60s)

- `bdata scraper heal c_fixture "100% of rows have an empty body_text field — the content extraction is broken, probably because the page layout changed. Please fix the body_text extraction for this site."`
- Show the AI-generated diff, approve: `bdata scraper approve c_fixture`.
- Re-run refresh → rows recovered, healthy.
- Ask the chatbot the same question again → answer is back. Same Collector ID, nothing downstream changed.

## 7: Close (10s)

- "FreshDocs: docs that stay fresh, scrapers that fix themselves. Built on Bright Data Scraper Studio."
- Repo link + example outputs on screen.

## Recording notes

- Mask or use a throwaway Bright Data API token if any UI shows env config.
- Keep terminal font large; use `--pretty` for readable JSON.
- If recording in one take: pre-warm all tabs, and have break/restore fixture commits staged.
