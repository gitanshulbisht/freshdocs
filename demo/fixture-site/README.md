# Fixture Docs — for the self-healing demo

This tiny static site exists so we can **demonstrate the break → heal → recover loop deterministically**. We control it: we push a "redesign" commit that renames the HTML containers/CSS classes the scraper depends on, watch the collector return empty rows, heal it with `bdata scraper heal`, approve, and re-run — same Collector ID, chatbot answers recovered.

Deploy to GitHub Pages and point the `fixture` collector at `<org>.github.io/freshdocs-fixture/sitemap.xml`.

## Pages

- index.html — overview
- install.html — install guide
- api.html — API reference
- troubleshooting.html — troubleshooting guide

## Break the scraper

Run `scripts/break_fixture.sh` (or manually): it renames `class="content"` → `class="content-v2"`, `class="title"` → `class="page-heading"`, and swaps `<h1>` → `<h2>` on every page — the classic "small site change breaks every selector" scenario from the hackathon brief.
