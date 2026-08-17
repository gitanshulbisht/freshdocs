# FreshDocs — Self-Healing Multi-Source Docs RAG Chatbot

One chatbot that answers from the *latest* docs across Docker, Kubernetes, AWS EKS, Argo Workflows (CI/CD), and LangChain (AI) — with citations — powered by custom Bright Data Scraper Studio Sitemap scrapers that re-run on schedule, detect changes, incrementally re-embed only what changed, and **self-heal** when a docs site redesigns.

Built for the [Into the Scrape-Verse](https://www.wemakedevs.org/hackathons/scrape-verse) hackathon (WeMakeDevs x Bright Data, Aug 17–23, 2026).

## Problem

Docs sites ship changes constantly (Docker's sitemap shows pages modified the same week). RAG pipelines are usually static: built once, then silently stale. FreshDocs keeps the knowledge base fresh automatically and repairs its own scrapers when sites change.

## Architecture

```
GitHub Actions (cron) ──trigger──▶ Bright Data Scraper Studio (Sitemap collectors c_* x5)
        ▲                                     │
        │ poll/validate/heal                  ▼ structured rows
        └──────────── Ingestion Service (Python/FastAPI)
                      diff → chunk → embed → ChromaDB + SQLite
                                              │
                                              ▼
                              Web UI: chat + citations + freshness panel
```

## Setup

1. **Bright Data account** — sign up (free tier, 5000 credits/month), enter promo `wemakedevs` in billing, create an API token in Account Settings.
2. **Collectors** — one per source (see `collectors/collectors.json` for prompts and IDs):
   ```bash
   npx -p @brightdata/cli bdata login
   bdata scraper create <sitemap_url> "<fields>"
   ```
3. **Environment** — copy `.env.example` to `.env`, fill in `BRIGHT_DATA_API_TOKEN`, `BRIGHT_DATA_COLLECTOR_IDS`, `OPENAI_API_KEY`.
4. **Install & run**:
   ```bash
   uv venv && uv pip install -r requirements.txt
   bash scripts/run_refresh.sh --full   # scrape all sources, index, embed
   uvicorn src.freshdocs.main:app --reload
   ```
   Open http://localhost:8000.

## How Bright Data Scraper Studio is used

- **5 custom Sitemap scrapers** (Docker, Kubernetes, AWS EKS, Argo Workflows, LangChain) created via the Bright Data CLI / AI Agent — none of these targets exist in the pre-built scrapers library.
- The `c_*` Collector IDs are treated as production APIs: the scheduler triggers them with `POST /dca/trigger` and polls `GET /dca/dataset`.
- **Self-healing**: nightly refresh validates output (row counts, empty-body rates). On failure it writes a symptom description and runs `bdata scraper heal <collector_id> "<what broke>"` + `bdata scraper approve` — same Collector ID, nothing downstream changes. The demo replays this on a fixture site we control.

## Repo layout

- `src/freshdocs/` — brightdata client, schemas, ingest/chunk, embed, diff, health, heal, RAG, FastAPI app
- `scripts/` — `run_refresh.sh` (CI entrypoint), `setup_collectors.sh`
- `collectors/collectors.json` — source registry (sitemap URLs, collector IDs, create prompts)
- `data/outputs/` — example structured output from the scrapers
- `tests/` — unit tests (chunking, diff, health rules, mocked Bright Data client)
- `demo/fixture-site/` — GitHub Pages fixture used to demonstrate the break→heal→recover loop
- `.github/workflows/refresh.yml` — nightly freshness refresh + heal-on-failure

## Rules compliance

Public docs pages only · custom scrapers · collector IDs wired into a real pipeline · example output committed · AI-assistant usage disclosed.

---

*AI coding assistants were used during development; the team has reviewed and understands all submitted code.*
