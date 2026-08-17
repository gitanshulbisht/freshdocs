from freshdocs.health import check_scrape
from freshdocs.schemas import SourceConfig


def make_source(expected: int) -> SourceConfig:
    return SourceConfig(key="docker", category="DevOps", name="Docker Docs",
                        sitemap_url="https://docs.docker.com/sitemap.xml",
                        collector_id="c_test", expected_urls=expected)


def make_rows(n: int, empty_body: int = 0, empty_title: int = 0) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "url": f"https://docs.docker.com/p/{i}",
            "title": "" if i < empty_title else f"Page {i}",
            "body_text": "" if i < empty_body else f"Body content for page {i}.",
        })
    return rows


def test_healthy_scrape_passes():
    report = check_scrape(make_source(100), make_rows(95))
    assert report.ok
    assert report.rows == 95
    assert not report.failures


def test_too_few_rows_fails_with_heal_symptom():
    report = check_scrape(make_source(1000), make_rows(12))
    assert not report.ok
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert "returned 12 rows" in failure.symptom
    assert failure.collector_id == "c_test"


def test_empty_bodies_fail():
    report = check_scrape(make_source(100), make_rows(100, empty_body=20))
    assert not report.ok
    assert any("empty body_text" in f.symptom for f in report.failures)


def test_empty_titles_fail():
    report = check_scrape(make_source(100), make_rows(100, empty_title=15))
    assert not report.ok
    assert any("empty title" in f.symptom for f in report.failures)


def test_exactly_at_threshold_passes():
    # 5% empty bodies is allowed; 6% is not.
    ok_report = check_scrape(make_source(100), make_rows(100, empty_body=5))
    assert ok_report.ok
    bad_report = check_scrape(make_source(100), make_rows(100, empty_body=6))
    assert not bad_report.ok
