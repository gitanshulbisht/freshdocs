from freshdocs.diff import diff_pages, fresh_hashes


def test_diff_detects_added_changed_removed():
    old = {"a": "hash-a", "b": "hash-b", "c": "hash-c"}
    new = {"a": "hash-a", "b": "hash-b2", "d": "hash-d"}
    result = diff_pages(old, new)
    assert result.added == ["d"]
    assert result.changed == ["b"]
    assert result.removed == ["c"]
    assert result.unchanged == 1
    assert result.reembed == ["d", "b"]


def test_diff_identical_is_empty():
    old = {"a": "hash-a", "b": "hash-b"}
    result = diff_pages(old, dict(old))
    assert result.total_changes == 0
    assert result.unchanged == 2


def test_fresh_hashes_normalizes_fields():
    rows = [
        {"url": "https://x.com/1", "body_text": "content one"},
        {"url": "https://x.com/2", "body": "content two"},
        {"url": "", "body_text": "no url, skipped"},
        {"url": "https://x.com/3", "body_text": "   "},  # empty body still hashed
    ]
    hashes = fresh_hashes(rows)
    assert set(hashes) == {"https://x.com/1", "https://x.com/2", "https://x.com/3"}
    assert fresh_hashes([{"url": "https://x.com/1", "body_text": "content one"}])["https://x.com/1"] \
        == hashes["https://x.com/1"]


def test_diff_exact_boundary_of_reembed():
    old = {"a": "h1", "b": "h2"}
    new = {"a": "h1", "b": "h2"}
    result = diff_pages(old, new)
    assert result.reembed == []
