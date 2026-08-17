from freshdocs.ingest import chunk_markdown, html_to_markdown, page_to_chunks, split_sections


def test_html_strips_boilerplate():
    html = """
    <html><body>
      <nav>Some nav junk</nav>
      <script>alert(1)</script>
      <h1>Installing Docker</h1>
      <p>Run the installer and follow the prompts.</p>
      <footer>Footer junk</footer>
    </body></html>
    """
    markdown = html_to_markdown(html)
    assert "Installing Docker" in markdown
    assert "Run the installer" in markdown
    assert "nav junk" not in markdown
    assert "alert(1)" not in markdown
    assert "Footer junk" not in markdown


def test_split_sections_attaches_heading():
    markdown = """# One
alpha content
## Two
beta content
# Three
gamma content
"""
    sections = split_sections(markdown)
    assert sections == [("One", "alpha content"), ("Two", "beta content"), ("Three", "gamma content")]


def test_short_section_is_single_chunk_with_heading_context():
    chunks = chunk_markdown("# Networking\nUse a bridge network.")
    assert len(chunks) == 1
    assert chunks[0].text.startswith("Networking:")
    assert "bridge network" in chunks[0].text


def test_long_section_splits_with_overlap():
    body = ("This is sentence number one. " * 400)  # > TARGET_CHARS
    markdown = f"# Big page\n{body}"
    chunks = chunk_markdown(markdown)
    assert len(chunks) > 1
    assert all(c.heading == "Big page" for c in chunks)
    # Rejoining must preserve coverage (allowing for overlap).
    joined = "".join(c.text.replace("Big page: ", "") for c in chunks)
    assert "sentence number one" in joined


def test_page_to_chunks_end_to_end():
    html = "<html><body><h1>Intro</h1><p>Hello world of docs.</p></body></html>"
    chunks = page_to_chunks(html)
    assert len(chunks) == 1
    assert "Hello world of docs" in chunks[0].text
