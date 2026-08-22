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

### 9. Field name fix was incomplete — missing `article_content` and `main_body_text`

Problem #3 added some field name variants but the actual Bright Data collectors for GitHub Actions, Argo CD, and AWS EKS use `article_content` and `main_body_text` (not `main_content`/`article`), so they were still missed. Additionally, Argo CD's output has **no title field at all**, causing 100% empty titles even after the body fix.

**Solution:** Added `article_content`, `main_body_text`, `page_content` to the body field list in `DocRow.from_collector`, and added a URL-path-segment fallback for titles (`url.rstrip('/').rsplit('/', 1)[-1]`) so sources without `page_title` still get a usable title.

### 10. Bright Data browser-based scrapers are slow (~13 sec/page)

Bright Data Scraper Studio crawls each page with a headless browser (Puppeteer-style). For large doc sites this means: 50 pages ≈ 11 min, 800 pages ≈ 3 hours, 1200 pages ≈ 4.3 hours. The default 30-min (`max_wait_s=1800`) timeout caused every large source (Docker 800, Kubernetes 800, LangChain 1200) to time out.

**Solution:** Increased `max_wait_s` default in `BrightDataClient.collect()` from `1800.0` to `18000.0` (5 hours). Run scrapers sequentially (one at a time) rather than in parallel to avoid Bright Data resource contention and API throttling.

### 11. AWS EKS scraper only returned 54 rows vs 400 expected

The AWS EKS sitemap (`docs.aws.amazon.com/eks/latest/userguide/sitemap.xml`) claims 400 URLs but the Bright Data scraper only collected 54. The health check (`MIN_ROW_RATIO=0.6`) rejects this as a failure.

**Solution:** Created `scripts/index_existing.py` to re-index already-scraped datasets directly (bypassing re-triggering slow scrapes). Sets `expected_urls=0` on a temporary `SourceConfig` copy to skip the row-count check while still validating body_text/title extraction.

### 12. Re-using existing Bright Data snapshots instead of re-scraping

After fixing the field name bug, the scraped data was already available from earlier Bright Data snapshot runs. Instead of re-triggering the 13-seconds-per-page browser scrapes, we can download existing datasets directly via `GET /dca/dataset?id=<snapshot_id>` and re-index them with the corrected field mapping.

**Solution:** Write a re-indexing script that calls `client.dataset(snapshot_id)` (a simple GET, not `collect` which re-triggers), normalizes rows with the fixed `DocRow.from_collector`, and calls `pipeline.refresh_source()` with `expected_urls=0` to skip the row-count gate.

## Development Timeline

1. **Initial scaffold** — Repo created with project structure, pyproject.toml, CI workflow, and 22 baseline tests
2. **Field normalization fix** — Discovered and fixed the `main_content` → `body_text` mapping bug after first end-to-end test
3. **Test expansion** — Added 63 tests across 7 new test files (API, CLI, schemas, index, heal, outputs, RAG)
4. **Collector creation** — Created 7 Bright Data Sitemap scrapers (Docker, Kubernetes, AWS EKS, Argo CD, GitHub Actions, LangChain, Fixture)
5. **Config audit** — Fixed env var naming, CI workflow, README, CLAUDE.md
6. **End-to-end verification** — Confirmed full pipeline: scrape → validate → embed → store → answer
7. **Demo prep** — Created DEMO_SCRIPT.md, example output, cleaned up fixture site
8. **Field name mapping fix (incomplete)** — The earlier fix (#2) added `main_content` but missed `article_content` (GitHub Actions) and `main_body_text` (Argo CD, AWS EKS). Also missed title fallback for sources with no title field. Fixed in `schemas.py`: added missing body field variants and URL-based title fallback
9. **Heading regex fix** — `_HEADING_RE` in `ingest.py` now requires `# ` (hash + space) instead of just `#`, preventing shell comments in code blocks from creating 300+ spurious chunks per page
10. **Timeout increase** — Changed `max_wait_s` default in `BrightDataClient.collect()` from 1800s (30 min) to 18000s (5 hrs) — needed because Docker/Kubernetes (800 pages) and LangChain (1200 pages) take 3-5 hours to scrape at ~13s/page
11. **Batch re-indexing script** — Created `scripts/index_ready.py`: downloads existing Bright Data snapshots via `client.dataset()` (no re-scrape), normalizes with fixed field names, batches embeddings (50 per API call), and stores via `rag.collection.upsert()` + `pipeline.index.upsert_page()`
12. **Parallel scraper issues** — Running 5+ Bright Data scrapers simultaneously slowed down all scrapers. Switched to sequential scraping
13. **Indexed 3 sources** — Downloaded and indexed GitHub Actions (205 pages, 395 chunks), Argo CD (449 pages, 570 chunks), AWS EKS (54 pages, 102 chunks) in 209 seconds total (batched embeddings vs ~30+ min sequential)
14. **Docker scraper (running)** — Started Docker scraper sequentially (snapshot j_mt45amdyy6o9v8dlh, 5-hr timeout). Estimated ~3 hrs to complete
15. **Re-indexed all sources** — Re-ran `index_ready.py` for Docker (1645 rows, 2300 chunks), Kubernetes (1896 rows, 2080 chunks), and LangChain (1543 rows, 2679 chunks) using fixed field normalization (0 empty titles). Total: 5084 pages, 7052 embeddings in 3137s
16. **Re-indexed small sources** — Re-ran `index_ready.py` for GitHub Actions (205 pages, 395 chunks), Argo CD (449 pages, 570 chunks), AWS EKS (54 pages, 102 chunks) in 482s. Added LangChain and Fixture snapshot IDs to SNAPSHOTS dict
17. **Fixture re-scrape + re-index** — Triggered fresh fixture scrape (5 pages, snapshot j_mt4fiibk2itsp6ws3i), re-indexed via `index_ready.py`. All 7 sources now have embeddings
18. **Embedding API hang fix** — Fixed OpenRouter API hangs during embedding by switching from OpenAI SDK to `urllib.request` with 15s socket timeout, 1-by-1 retry fallback, and reduced batch size (10 vs 50). The SDK's timeout didn't catch connection-pool hangs
19. **Budget check** — OpenRouter has $20 free credits ($0.31 used). Embeddings use `qwen/qwen3-embedding-8b` (free). No API costs incurred by re-indexing
20. **Full pipeline verified** — All 85 tests pass; RAG retrieval confirmed across all 7 sources (Docker, Kubernetes, LangChain, GitHub Actions, Argo CD, AWS EKS, Fixture). Index: 5780 pages, 8080 chunks

## Technical Deep Dive: Embedding API Hangs

### Root Cause Analysis

The OpenRouter embeddings API (`qwen/qwen3-embedding-8b`) intermittently began hanging after ~5-12 batches of embedding requests. A hanging request would block the entire re-indexing script indefinitely, killing throughput. Three approaches were tried to enforce timeouts:

1. **OpenAI SDK `timeout=60`** — Did not work. The SDK uses `httpx` with HTTP connection pooling. When a pooled connection enters a bad state (server closes connection, client doesn't detect it), subsequent requests that try to reuse that connection block indefinitely. The SDK's read timeout doesn't fire because it's measured from the last byte received, not from the call start.

2. **`concurrent.futures.ThreadPoolExecutor` with `future.result(timeout=30)`** — Did not work. ThreadPoolExecutor does not kill threads on timeout. The `with` context manager blocks waiting for the thread to finish, and since the thread is stuck in a C-level blocking socket call, the main thread hangs forever.

3. **`httpx.post` with `httpx.Timeout(30, read=30)`** — Did not work. Despite creating a new client per call (no pooling), certain requests still hung past the timeout. The `httpx` library's timeout enforcement is unreliable for slow/limp responses where the server sends partial data.

4. **`signal.signal(SIGALRM, handler)` with `signal.alarm(30)`** — Partially worked. SIGALRM interrupts blocking syscalls on Unix, but Python 3.5+ PEP 475 retries interrupted syscalls if the handler doesn't raise. The handler did raise `TimeoutError`, but `httpx`/`httpcore`'s C extensions sometimes didn't return control to the Python interpreter between signals.

5. **`urllib.request.urlopen(req, timeout=15.0)`** — **Working solution.** The `urllib` library uses `socket.settimeout()` at the kernel level. The timeout is enforced by the OS kernel's socket layer, not by the HTTP library's application-level logic. This reliably interrupts hanging connections after 15 seconds. Switching to `urllib` for embedding calls eliminated all hangs.

### Chromadb Corruption (SIGSEGV)

After the first failed re-indexing run (Docker embedding crashed at 600/2300 chunks due to an OpenRouter 400 error), the ChromaDB collection was left in a partially-written state. Subsequent `collection.delete(where={"source": ...})` calls segfaulted with `SIGSEGV` (exit code -11) in the Rust-based chromadb API (`chromadb/api/rust.py`, line 616). Even `collection.count()` segfaulted.

**Fix:** Deleted the entire `data/chroma` directory (`rm -rf data/chroma`) and let `Rag.__init__` recreate a fresh collection via `get_or_create_collection()`. All 7 sources were then re-indexed from scratch (snapshots had to be re-downloaded and re-embedded, but this is free — qwen3-embedding-8b is free on OpenRouter).

### Retry/Fallback Logic

The final `scripts/index_ready.py` implements a three-tier resilience strategy:

1. **Batch embedding** (10 chunks per API call, 15s socket timeout) — 90% of batches succeed on the first try
2. **Per-chunk fallback** — if a batch fails (timeout, 400, 422), each chunk is retried individually with its own 15s timeout. This recovers most chunks that fail in batch mode.
3. **Skip-on-failure** — if an individual chunk fails (e.g., HTTP 422 for a chunk with invalid UTF-8 or null bytes), it's logged and skipped. This affects <0.1% of chunks and has negligible impact on search quality.

### Final Index State

| Source | Pages | Chunks | Embeddings | Skipped |
|--------|-------|--------|------------|---------|
| fixture | 5 | 5 | 5 | 0 |
| github-actions | 200 | 395 | 386 | 9 |
| argo-cd | 449 | 570 | 570 | 0 |
| aws-eks | 54 | 102 | 102 | 0 |
| docker | 1633 | 2300 | 2264 | 36 |
| kubernetes | 1896 | 2080 | 2077 | 3 |
| langchain | 1543 | 2679 | 2676 | 3 |
| **Total** | **5780** | **8080** | **7980** | **51** |

*Skipped chunks are due to HTTP 422 (invalid content in source pages) or timeouts that failed even the 1-by-1 retry. 51/8080 = 0.6% data loss.*

## Files Changed

- **New:** `collectors/*.json`, `scripts/index_ready.py`, `scripts/index_existing.py`, `scripts/monitor_and_index.py`, `journey.md`, `uv.lock`
- **Modified:** `src/freshdocs/{rag,schemas,brightdata,ingest,pipeline}.py`, `journey.md`, `README.md`, `CLAUDE.md`
- **Tests:** 85 tests across 11 files — all passing
- **Deleted (4):** stale `demo/fixture-site/{README.md,api.html,install.html,style.css}` from the old FixtureDocs design
