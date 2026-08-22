# FreshDocs — Self-Healing Multi-Source Docs RAG Chatbot

One chatbot that answers from the *latest* docs across Docker, Kubernetes, AWS EKS, Argo CD (CI/CD), GitHub Actions (CI/CD), and LangChain (AI) — with citations — powered by custom Bright Data Scraper Studio Sitemap scrapers that re-run on schedule, detect changes, incrementally re-embed only what changed, and **self-heal** when a docs site redesigns.

Built for the [Into the Scrape-Verse](https://www.wemakedevs.org/hackathons/scrape-verse) hackathon (WeMakeDevs x Bright Data, Aug 17–23, 2026). [GitHub repo](https://github.com/gitanshulbisht/freshdocs)

## Problem

Docs sites ship changes constantly — Docker's sitemap, for example, shows pages modified the same week. Traditional RAG pipelines are static: built once, then silently stale. FreshDocs keeps the knowledge base fresh automatically and repairs its own scrapers when sites change their HTML layout or field naming.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub Actions (cron)                         │
│                         nightly @ 03:00 UTC                          │
└────────────┬──────────────────────────────────────────────┬────────┘
             │ trigger (POST /dca/trigger)                  │ poll (GET /dca/dataset)
             ▼                                                ▼
  ┌──────────────────┐                              ┌──────────────────┐
  │ Bright Data      │                              │ Bright Data      │
  │ Scraper Studio   │──structured rows──▶          │ Scraper Studio   │
  │ (7 Sitemap       │  [{url,title,body,...}]      │ (7 Sitemap       │
  │  collectors c_*) │                              │  collectors c_*) │
  └────────┬─────────┘  │                              │                │
           │            │                              │                │
           │ heal/approve (bdata CLI)                  │                │
           └────────────┼──────────────────────────────┼────────────────┘
                        │                              │
                        ▼                              ▼
              ┌──────────────────────────────────────────────────┐
              │              Ingestion Service (Python)           │
              │  freshdocs.pipeline.Pipeline                     │
              │                                                  │
              │  1. DocRow.from_collector() — normalize fields   │
              │  2. check_scrape() — validate row/body/title     │
              │  3. Diff vs SQLite (change detection)            │
              │  4. html_to_markdown() — strip boilerplate       │
              │  5. chunk_markdown() — heading-aware splitter    │
              │  6. embed_texts() — qwen3-embedding-8b (1024D)   │
              │  7. ChromaDB.upsert() + SQLite insert           │
              └──────────────────────────────────────────────────┘
                        │
                        ▼
              ┌────────────────────────────────────────┐
              │         Query Path (FastAPI)           │
              │   GET /api/ask  →  Rag.answer()        │
              │   1. embed_texts(query)                │
              │   2. ChromaDB.query (cosine, top_k=6)  │
              │   3. LLM chat (deepseek-v4-flash)      │
              │   4. Extract citations from [1][3] refs │
              └────────────────────────────────────────┘
```

### Data Flow

1. **Scrape** — Bright Data Scraper Studio visits each sitemap URL with a headless browser, follows internal links, and extracts `{url, title, body_text, ...}` for each page. The browser renders JavaScript so SPA docs (like Docker's) are fully captured.

2. **Download** — The Ingestion Service polls `GET /dca/dataset?id=<snapshot_id>` until the snapshot reaches `snapshot` status, then downloads all rows as a JSON array. This is a simple GET — no re-scraping.

3. **Normalize** — `DocRow.from_collector()` maps Bright Data's inconsistent field names to a canonical schema:
   - **URL**: `url` → `canonical_url` → `page_url` → `product_page_url` → `input.url`
   - **Body**: `body_text` → `main_content` → `article_content` → `main_body_text` → `page_content` → `content` → `text` → `body`
   - **Title**: `title` → `page_title` → `name` → `heading` → URL-path fallback (`url.rstrip('/').rsplit('/', 1)[-1]`)
   - **Last updated**: `last_updated` → `lastUpdated` → `last_modified_date` → `modified` → `updated_at`

4. **Health check** — `check_scrape()` validates that ≥60% of expected URLs were collected and that ≥10% of rows have non-empty `body_text`. Failures carry a symptom string fed to the Bright Data CLI's `bdata scraper heal` command.

5. **Chunk** — `html_to_markdown()` strips `<script>/<style>/<nav>/<footer>` boilerplate and converts to markdown. `split_sections()` splits on ATX headings (`#`, `##`, etc.) — but the regex `^#{1,6}(\s+|$)` requires a space after `#` to avoid treating shell comments (`#!/bin/bash`) as headings. `chunk_markdown()` splits sections >2000 chars with 200-char overlap.

6. **Embed** — Each chunk is embedded via OpenRouter's `qwen/qwen3-embedding-8b` (1024-dimensional vectors, cosine distance). Embeddings are batched (10 per API call with 15s socket timeout via `urllib.request` — see `journey.md` → "Technical Deep Dive: Embedding API Hangs" for why the OpenAI SDK's timeout was unreliable).

7. **Store** — Embeddings go to ChromaDB (persistent, HNSW index with cosine distance); page metadata goes to SQLite (`data/index.sqlite`) for change detection on the next run.

8. **Answer** — At query time, the user's question is embedded, top-6 similar chunks are retrieved via ChromaDB's HNSW search, and DeepSeek V4 generates a concise answer with bracketed citations `[1][3]` that map back to source URLs.

### Self-Healing Mechanism

When a nightly refresh detects a health check failure (e.g., 100% empty `body_text` because the scraper's field names don't match the normalizer):

1. **Symptom capture** — The exact failure (row count, empty body rate) is formatted as a human-readable string.
2. **Heal** — `bdata scraper heal <collector_id> "<symptom>"` tells the Bright Data AI agent to fix the scraper's extraction logic.
3. **Approve** — `bdata scraper approve <collector_id>` deploys the healed scraper.
4. **Re-run** — The healed scraper produces corrected field names, which `DocRow.from_collector()` normalizes correctly, so health checks pass.

This loop is demonstrated on the `demo/fixture-site` — `scripts/break_fixture.sh` intentionally breaks the scraper (corrupting CSS selectors), and the pipeline detects the failure, heals, and recovers.

## Setup

1. **Bright Data account** — sign up (free tier, 5000 credits/month), enter promo `wemakedevs` in billing, create an API token in Account Settings.
2. **OpenRouter account** — sign up for free (free credits available), create an API key.
3. **Collectors** — one per source (see `collectors/collectors.json` for IDs and prompts):
   ```bash
   npx -y -p @brightdata/cli bdata login       # once
   bash scripts/setup_collectors.sh --execute  # creates all 7 collectors
   ```
4. **Environment** — copy `.env.example` to `.env`, fill in:
   - `BRIGHT_DATA_API_TOKEN` — Bright Data API token
   - `BRIGHT_DATA_COLLECTOR_IDS` — comma-separated collector IDs (from collectors.json)
   - `OPENROUTER_API_KEY` — OpenRouter API key
   - `FRESHDOCS_LLM_PROVIDER` — `openrouter` (default) or `openai`
   - `FRESHDOCS_OPENROUTER_EMBEDDING_MODEL` — `qwen/qwen3-embedding-8b` (default)
   - `FRESHDOCS_OPENROUTER_CHAT_MODEL` — `deepseek/deepseek-v4-flash-0731` (default)
5. **Install & run**:
   ```bash
   uv venv && uv pip install -e .
   uvicorn freshdocs.main:app --reload
   ```
   Open http://localhost:8000.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Static web UI (chat + sources + freshness panel) |
| `GET` | `/api/sources` | List all 7 source configs (name, category, sitemap URL) |
| `POST` | `/api/ask` | Ask a question; body `{"question": "...", "sources": ["docker","kubernetes"]?}` |
| `GET` | `/api/status` | Index freshness: per-source page counts and last refresh timestamps |
| `GET` | `/static/*` | Static assets (CSS, JS) for the web UI |

## CLI Commands

```bash
# Full refresh: scrape all sources, validate, heal if needed, embed, store
freshdocs refresh --full

# Refresh a single source
freshdocs refresh --source docker

# Dry-run mode: scrape + diff, report what changed, write nothing
freshdocs refresh --dry-run

# Re-index from existing Bright Data snapshots (no re-scrape)
python scripts/index_ready.py --sources docker kubernetes langchain

# Trigger self-healing on a source with known issues
freshdocs heal --source docker "The body_text field is empty for all rows"

# Answer a question directly from CLI
freshdocs answer "How do I run a Docker container?" --sources docker kubernetes
```

## Indexing at Scale

Large doc sites (Docker: 800 pages, Kubernetes: 800 pages, LangChain: 1200 pages) take 3-5 hours to scrape at ~13s/page (Bright Data's headless browser renders each page). Key techniques for handling this:

- **Sequential scraping** — run one scraper at a time to avoid Bright Data resource contention
- **5-hour timeout** — `max_wait_s=18000` (up from 1800) accommodates the slowest sources
- **Snapshot reuse** — `scripts/index_ready.py` downloads existing datasets via `GET /dca/dataset` instead of re-scraping (free, fast)
- **Batched embeddings** — 10 chunks per API call with `urllib.request` (15s socket timeout) and 1-by-1 retry fallback for failed batches
- **ChromaDB reset** — `rm -rf data/chroma` recreates the vector store from scratch if corruption occurs

### Final Index State (5780 pages, 8080 chunks, 7980 embeddings)

| Source | Pages | Chunks | Embeddings | Skipped | Notes |
|--------|-------|--------|------------|---------|-------|
| fixture | 5 | 5 | 5 | 0 | Demo site (github.io) |
| github-actions | 200 | 395 | 386 | 9 | API token limit on some chunks |
| argo-cd | 449 | 570 | 570 | 0 | |
| aws-eks | 54 | 102 | 102 | 0 | Only 54 of ~400 URLs collected |
| docker | 1633 | 2300 | 2264 | 36 | 12 pages with empty bodies |
| kubernetes | 1896 | 2080 | 2077 | 3 | |
| langchain | 1543 | 2679 | 2676 | 3 | |

## Repo Layout

- `src/freshdocs/` — core modules:
  - `brightdata.py` — Bright Data Scraper Studio API client (trigger, poll, dataset download, balance check)
  - `schemas.py` — Pydantic models: `DocRow`, `SourceConfig`, `Registry`, `HealthCheckFailure`, `Answer`, `Citation`, `SourceStatus`
  - `ingest.py` — HTML→markdown conversion (`html_to_markdown`), heading-aware chunking (`chunk_markdown`, `split_sections`)
  - `index.py` — SQLite page index with content-hash-based change detection
  - `pipeline.py` — `Pipeline` class orchestrating collect→normalize→validate→diff→chunk→embed→store→heal
  - `rag.py` — `Rag` class: OpenAI/OpenRouter client, ChromaDB vector store (cosine/HNSW), retrieval + LLM answer with citations
  - `cli.py` — Typer CLI: `refresh`, `heal`, `answer`, `status`
  - `main.py` — FastAPI app with `/api/ask`, `/api/sources`, `/api/status` + static web UI
  - `static/` — HTML/CSS/JS for the web UI
- `collectors/` — Bright Data Scraper Studio collector definitions (sitemap URLs, create prompts, IDs)
- `collectors/collectors.json` — Source registry (7 sources: Docker, Kubernetes, AWS EKS, Argo CD, GitHub Actions, LangChain, Fixture)
- `scripts/` — `run_refresh.sh`, `setup_collectors.sh`, `break_fixture.sh`, `restore_fixture.sh`, `index_ready.py`, `index_existing.py`, `monitor_and_index.py`
- `data/` — SQLite index (`data/index.sqlite`), ChromaDB vector store (`data/chroma/`)
- `data/outputs/` — example structured output from scrapers
- `tests/` — 85 tests across 11 files (chunking, schemas, health, index, heal, RAG, API, CLI, mock Bright Data, pipeline)
- `demo/fixture-site/` — GitHub Pages fixture for the break→heal→recover demo
- `.github/workflows/refresh.yml` — nightly freshness refresh + heal-on-failure
- `pyproject.toml` — dependencies and CLI entry point (`freshdocs = "freshdocs.cli:main"`)

## Testing

```bash
uv run python -m pytest tests/ -q    # 85 tests, ~12s
```

Test coverage includes:
- **schemas**: field name normalization across all Bright Data field variants
- **ingest**: heading-aware chunking, overlap boundaries, shell comment handling
- **index**: SQLite page storage and change detection via content hashes
- **heal**: self-healing command construction and dry-run guards
- **rag**: retrieval ranking, citation extraction from LLM output
- **api**: endpoint responses, source list, ask with/without source filters
- **cli**: refresh, heal, answer, status commands (mocked Bright Data client)
- **outputs**: consistency between scraper output and `DocRow` normalization
- **pipeline**: full collect→validate→health-check flow with mocked Bright Data

## Rules Compliance

Public docs pages only · custom scrapers · collector IDs wired into a real pipeline · example output committed · AI-assistant usage disclosed.

---

*AI coding assistants (Claude via CommandCode) were used during development; the team has reviewed and understands all submitted code.*
