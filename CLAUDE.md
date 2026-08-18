# FreshDocs — coding agent rules

Bright Data Scrape-Verse hackathon project. Multi-source docs RAG chatbot powered by Bright Data Scraper Studio Sitemap collectors.

## Pinned Collector IDs (do NOT recreate scrapers)

Run `bdata scraper run <collector_id> <sitemap_url>` or trigger via the API. If a scraper breaks, use `bdata scraper heal <collector_id> "<what broke>"` then `bdata scraper approve <collector_id>` — never `scraper create` again (the Collector ID must stay stable; downstream depends on it).

| Source | Collector ID |
|---|---|
| docker | `c_msy8jxs51evybyw114` |
| kubernetes | `c_msygh24z9gew9y4g5` |
| aws-eks | `c_msyhh3a6292e0hhfwe` |
| argo-cd | `c_msyg8e3d240gd99n4h` |
| github-actions | `c_msyhyf8e2nic9gcflv` |
| langchain | `c_msyfibfq1rricg2xtx` |
| fixture | `c_msya0kbloj7pqkjkj` |

## Working with the Bright Data CLI

```bash
npx -p @brightdata/cli bdata login                 # OAuth, once
bdata scraper create <url> "<what to extract>"      # AI generates scraper (5-15 min)
bdata scraper run <collector_id> <url> --pretty     # run + structured JSON
bdata scraper heal <collector_id> "<what broke>"    # AI proposes fix
bdata scraper approve <collector_id>                # accept fix (--reject to discard)
```

## API (programmatic)

- Trigger: `POST https://api.brightdata.com/dca/trigger?collector=<id>&queue_next=1` with `Authorization: Bearer <token>`, body = JSON array of `{"url": "https://...sitemap.xml"}` → `{"collection_id": "j_..."}`
- Poll: `GET https://api.brightdata.com/dca/dataset?id=<snapshot_id>` every 5s until response is a JSON array.

## Project conventions

- Python 3.11+, venv via `uv`; deps in requirements.txt
- Env vars: `BRIGHT_DATA_API_TOKEN`, `BRIGHT_DATA_COLLECTOR_IDS` (JSON map), `OPENROUTER_API_KEY` (or `OPENAI_API_KEY` if provider=openai) — from `.env`, never committed
- Source registry: `collectors/collectors.json` (update collector IDs here too)
- Tests: `pytest`; keep the Bright Data client and health rules covered
