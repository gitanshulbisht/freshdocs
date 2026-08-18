# FreshDocs Development Journey

Multi-source self-healing docs RAG chatbot built for the [Into the Scrape-Verse](https://www.wemakedevs.org/hackathons/scrape-verse) hackathon (WeMakeDevs x Bright Data).

## Summary

One chatbot answers from the latest docs across Docker, Kubernetes, AWS EKS, Argo CD, GitHub Actions, and LangChain — powered by Bright Data Scraper Studio Sitemap scrapers that re-run on schedule, detect changes, incrementally re-embed only what changed, and self-heal when a docs site redesigns its layout.

**Stack:** Bright Data Scraper Studio API · OpenRouter (embeddings + LLM) · ChromaDB (vector store) · SQLite (index) · FastAPI (web UI + API)

## Problems Faced & Solutions

### 1. Collector IDs out of sync across files

The Docker collector was created via the Bright Data CLI but its ID was never copied into `collectors/collectors.json` (left empty). The Fixture collector ID was also truncated (`c_msya0kbloj7pqkjk` vs the full `c_msya0kbloj7pqkjkj`). CLAUDE.md still showed all IDs as `*(pending)*`.

**Solution:** Read each `collectors/<source>.json` output file produced by `bdata scraper create`, cross-referenced the collector IDs, and updated `collectors.json` and `CLAUDE.md` to pin all 7 IDs in one place.

### 2. env var name mismatch caused pipeline to silently skip

The codebase reads `BRIGHT_DATA_COLLECTOR_IDS` (matching `BRIGHT_DATA_API_TOKEN`), but `.env.example`, `DEMO_SCRIPT.md`, and the CI workflow all used `BRIGHTDATA_COLLECTOR_IDS` (missing underscore). The pipeline fell back to the registry, so it worked by accident — but a user following the docs would be confused.

**Solution:** Audited all three files with grep, fixed to `BRIGHT_DATA_COLLECTOR_IDS` everywhere, and populated `.env` with the actual collector IDs for local development.

### 3. Health check failing on valid data (field name mismatch)

Bright Data scrapers output fields like `main_content`, `page_title`, `product_page_url`, and `last_modified_date`. The `DocRow.from_collector` normalizer handled some variants but was missing these. Meanwhile, the health check (`check_scrape`) only looked for `body_text` and `title` — so a perfectly valid scrape with 5 pages of content would fail 100% of health checks.

**Solution:**
- Added the missing Bright Data field name variants to `DocRow.from_collector` (e.g., `main_content`, `product_page_url`, `last_modified_date`)
- Normalized rows in `collect_source()` before health checks using `DocRow.from_collector().model_dump()`, so the health check sees standard field names regardless of the scraper's output schema

### 4. `--dry-run` triggering destructive healing

The CLI's `--dry-run` flag is meant for safe "scrape + diff, write nothing" testing. But `heal_and_approve` was called unconditionally when health checks failed — even in dry-run mode, it would call `bdata scraper heal` + `bdata scraper approve`, modifying the live Bright Data scraper.

**Solution:** Added a `not args.dry_run` guard so healing only runs in non-dry-run mode.

### 5. CI workflow couldn't import the package

The GitHub Actions workflow used `pip install -r requirements.txt` which installs dependencies but NOT the `freshdocs` package itself. So `python -m freshdocs.cli refresh` failed with `ModuleNotFoundError`. The README had the same issue — `uvicorn src.freshdocs.main:app` wouldn't work without `PYTHONPATH`.

**Solution:** Changed CI to `pip install -e .` and updated README to `uv pip install -e .` + `uvicorn freshdocs.main:app`.

### 6. Parallel collector creation hit concurrency cap

Ran 5 `bdata scraper create` commands simultaneously — 3 failed with `sprintf invalid format %j` errors (a bdata CLI parsing bug triggered by 500 responses under concurrency), and Kubernetes timed out at the 600-second polling limit.

**Solution:** Created collectors sequentially, one at a time. Used shorter prompts for readthedocs.io sites (which succeeded in under 5 minutes). For the GitHub Actions scraper — the general `docs.github.com/en/sitemap.xml` caused AI generation to fail — switched to the per-section `docs.github.com/en/actions/sitemap.xml` which succeeded.

### 7. Break/restore scripts didn't match the AcmeDB site

The original `break_fixture.sh`/`restore_fixture.sh` targeted CSS classes from the previous "FixtureDocs" design (`.content`, `.title`, `.body-text`, etc.). The AcmeDB fixture site uses semantic HTML with no CSS classes (`<article>`, `<h1>`, `<p>`, `<pre>`).

**Solution:** Rewrote both scripts for the AcmeDB HTML structure, using unique CSS class markers (e.g., `.content-v2`, `.page-heading`) to avoid tag-collision bugs on restore. Used `<h3>` instead of `<h2>` for the broken heading level (since the site already has h2 section headings — h2→h1 restore would clobber them).

### 8. Field normalization for end-to-end self-healing

During the first end-to-end test, the pipeline correctly detected the health failure ("100% of rows have an empty body_text field") and triggered `bdata scraper heal`. But the root cause wasn't broken data — it was a field name mismatch between what the scraper returns and what the health check expects.

**Solution:** The field normalization fix (#3) addressed this. After the fix, the healed scraper's output (`main_content`, `page_title`) is normalized to `body_text`, `title` before the health check runs, so valid data passes validation.

## Development Timeline

1. **Initial scaffold** — Repo created with project structure, pyproject.toml, CI workflow, and 22 baseline tests
2. **Field normalization fix** — Discovered and fixed the `main_content` → `body_text` mapping bug after first end-to-end test
3. **Test expansion** — Added 63 tests across 7 new test files (API, CLI, schemas, index, heal, outputs, RAG)
4. **Collector creation** — Created 7 Bright Data Sitemap scrapers (Docker, Kubernetes, AWS EKS, Argo CD, GitHub Actions, LangChain, Fixture)
5. **Config audit** — Fixed env var naming, CI workflow, README, CLAUDE.md
6. **End-to-end verification** — Confirmed full pipeline: scrape → validate → embed → store → answer
7. **Demo prep** — Created DEMO_SCRIPT.md, example output, cleaned up fixture site

## Files Changed

- **New (18):** 7 `collectors/*.json`, 7 `tests/test_*.py`, `data/outputs/fixture.json`, `demo/DEMO_SCRIPT.md`, `journey.md`
- **Modified (20):** `README.md`, `CLAUDE.md`, `collectors/collectors.json`, `.env.example`, `.env`, `.github/workflows/refresh.yml`, `src/freshdocs/{pipeline,main,rag,schemas}.py`, `scripts/*.sh`, 3 `demo/fixture-site/*` files, `tests/test_pipeline.py`
- **Deleted (4):** stale `demo/fixture-site/{README.md,api.html,install.html,style.css}` from the old FixtureDocs design
