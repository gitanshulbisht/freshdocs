"""Health rules: turn a fresh scrape into a pass/fail + symptom description.

The symptom text is written to be pasted straight into `bdata scraper heal`
so the loop is: scrape -> fail -> heal(collector, symptom) -> approve -> re-scrape.
"""

from __future__ import annotations

from .schemas import HealthCheckFailure, HealthReport, SourceConfig

MIN_ROW_RATIO = 0.6          # rows >= 60% of expected sitemap size
MAX_EMPTY_BODY_RATE = 0.05   # at most 5% of rows may have empty body text
MAX_EMPTY_TITLE_RATE = 0.10  # at most 10% of rows may have empty titles


def check_scrape(source: SourceConfig, rows: list[dict]) -> HealthReport:
    failures: list[HealthCheckFailure] = []

    expected = source.expected_urls
    got = len(rows)

    bodies = []
    titles = []
    for row in rows:
        body = (row.get("body_text") or row.get("body") or "").strip()
        title = (row.get("title") or "").strip()
        bodies.append(body)
        titles.append(title)

    if expected > 0 and got < expected * MIN_ROW_RATIO:
        failures.append(HealthCheckFailure(
            source=source.key,
            collector_id=source.collector_id,
            symptom=(
                f"The scraper returned {got} rows but the sitemap has about {expected} pages — "
                f"the collector is only extracting a small fraction of the pages."
            ),
            details={"rows": got, "expected": expected, "min_ratio": MIN_ROW_RATIO},
        ))

    if bodies:
        empty_body_rate = sum(1 for b in bodies if not b) / len(bodies)
        if empty_body_rate > MAX_EMPTY_BODY_RATE:
            failures.append(HealthCheckFailure(
                source=source.key,
                collector_id=source.collector_id,
                symptom=(
                    f"{empty_body_rate:.0%} of rows have an empty body_text field — "
                    f"the content extraction is broken, probably because the page layout changed. "
                    f"Please fix the body_text extraction for this site."
                ),
                details={"empty_body_rate": empty_body_rate, "limit": MAX_EMPTY_BODY_RATE},
            ))
    else:
        empty_body_rate = 1.0

    if titles:
        empty_title_rate = sum(1 for t in titles if not t) / len(titles)
        if empty_title_rate > MAX_EMPTY_TITLE_RATE:
            failures.append(HealthCheckFailure(
                source=source.key,
                collector_id=source.collector_id,
                symptom=(
                    f"{empty_title_rate:.0%} of rows have an empty title field — "
                    f"the title extraction is broken, probably because the page layout changed."
                ),
                details={"empty_title_rate": empty_title_rate, "limit": MAX_EMPTY_TITLE_RATE},
            ))

    return HealthReport(
        source=source.key,
        ok=not failures,
        rows=got,
        empty_body_rate=empty_body_rate,
        failures=failures,
    )
