"""HTML -> markdown -> heading-aware chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from markdownify import markdownify as md

# ~500 tokens per chunk at a rough 4 chars/token for prose; overlap keeps
# context across boundaries.
TARGET_CHARS = 2000
OVERLAP_CHARS = 200

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NEWLINE_RE = re.compile(r"\n{3,}")


@dataclass
class Chunk:
    text: str
    heading: str


def html_to_markdown(html: str) -> str:
    """Strip nav/footer/script/style boilerplate, convert the rest to markdown."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "form"]):
        tag.decompose()
    cleaned = str(soup)
    return md(cleaned, heading_style="ATX").strip()


def _clean(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) sections.

    Heading hierarchy is flattened: each heading starts a new section and the
    nearest preceding heading name is kept as context for the chunks it owns.
    """
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_heading, body))

    for line in markdown.splitlines():
        if line.startswith("#"):
            flush()
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return sections


def chunk_markdown(markdown: str) -> list[Chunk]:
    """Heading-aware chunking with overlap."""
    chunks: list[Chunk] = []
    for heading, body in split_sections(markdown):
        body = _clean(body)
        if not body:
            continue
        if len(body) <= TARGET_CHARS:
            chunks.append(Chunk(text=f"{heading}: {body}" if heading else body, heading=heading))
            continue

        start = 0
        while start < len(body):
            end = min(start + TARGET_CHARS, len(body))
            # Prefer breaking at a paragraph or sentence boundary.
            if end < len(body):
                window = body[start:end]
                paragraph_break = window.rfind("\n\n")
                sentence_break = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
                cut = max(paragraph_break, sentence_break)
                if cut > TARGET_CHARS // 2:
                    end = start + cut + 1
            text = body[start:end].strip()
            if text:
                chunks.append(Chunk(text=f"{heading}: {text}" if heading else text, heading=heading))
            start = max(end - OVERLAP_CHARS, start + 1)
    return chunks


def page_to_chunks(html: str) -> list[Chunk]:
    """Full pipeline: raw HTML page -> chunk list."""
    markdown = html_to_markdown(html)
    return chunk_markdown(markdown)
