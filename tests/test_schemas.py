"""Tests for schema normalization (DocRow.from_collector, SourceConfig)."""

from freshdocs.schemas import DocRow


def test_from_collector_standard_fields():
    row = DocRow.from_collector({
        "url": "https://example.com/page",
        "title": "Page Title",
        "body_text": "Page content here.",
        "last_updated": "2026-08-10",
    })
    assert row.url == "https://example.com/page"
    assert row.title == "Page Title"
    assert row.body == "Page content here."
    assert row.last_updated == "2026-08-10"


def test_from_collector_alternate_field_names():
    """Bright Data may return bodyText, body, content, text, etc."""
    row = DocRow.from_collector({
        "canonicalURL": "https://example.com/canonical",
        "bodyText": "From bodyText field.",
        "page_title": "Page Title",
        "updated_at": "2026-08-15",
    })
    assert row.url == "https://example.com/canonical"
    assert row.title == "Page Title"
    assert row.body == "From bodyText field."
    assert row.last_updated == "2026-08-15"


def test_from_collector_falls_back_to_input_url():
    """Some collectors nest the input under an 'input' key."""
    row = DocRow.from_collector({
        "input": {"url": "https://example.com/input-url"},
        "body": "From body field.",
        "name": "Name as title",
    })
    assert row.url == "https://example.com/input-url"
    assert row.title == "Name as title"
    assert row.body == "From body field."


def test_from_collector_empty_rows():
    row = DocRow.from_collector({"url": "", "title": "", "body_text": ""})
    assert row.url == ""
    assert row.title == ""
    assert row.body == ""


def test_from_collector_strips_whitespace():
    row = DocRow.from_collector({
        "url": "  https://example.com/page  ",
        "title": "  Spaced Title  ",
        "body_text": "  Content with spaces  ",
    })
    assert row.url == "https://example.com/page"
    assert row.title == "Spaced Title"
    assert row.body == "Content with spaces"


def test_from_collector_body_field_fallback_precedence():
    """first() should pick the first non-empty value from the fallback list."""
    row = DocRow.from_collector({
        "title": "Real Title",
        "name": "Fallback Name",
        "heading": "Another Fallback",
    })
    assert row.title == "Real Title"

    row2 = DocRow.from_collector({
        "name": "Fallback Name",
        "heading": "Another Fallback",
    })
    assert row2.title == "Fallback Name"


def test_from_collector_brightdata_field_spellings():
    """from_collector should handle the field names actually returned by Bright Data."""
    row = DocRow.from_collector({
        "product_page_url": "https://acme.example.com/docs",
        "page_title": "AcmeDB Docs",
        "main_content": "# AcmeDB Documentation\n\nDistributed SQL database.",
        "last_modified_date": "2026-08-15T12:00:00Z",
    })
    assert row.url == "https://acme.example.com/docs"
    assert row.title == "AcmeDB Docs"
    assert "Distributed SQL" in row.body
    assert row.last_updated == "2026-08-15T12:00:00Z"
