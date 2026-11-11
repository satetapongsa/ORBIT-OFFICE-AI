"""Split extracted text into overlapping passages for retrieval.

Character-based (Thai has no spaces between words, so token counts are unreliable): passages
are at most ``size`` characters, prefer to end at a paragraph, line or sentence boundary, and
overlap by about ``overlap`` characters so a fact split across a boundary is still found.
PDF pages are separated by form feeds (``\\f``) in the extracted text; each passage records the
page it starts on.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

PAGE_BREAK = "\f"
# Preferred cut points, best first; a cut is accepted only in the last 40 % of a window.
_BREAKS = (PAGE_BREAK, "\n\n", "\n", ". ", "。", " ", "\t")


@dataclass(frozen=True, slots=True)
class TextChunk:
    index: int
    content: str
    page: int | None


def _cut(text: str, start: int, end: int) -> int:
    floor = start + int((end - start) * 0.6)
    for mark in _BREAKS:
        pos = text.rfind(mark, floor, end)
        if pos != -1:
            return pos + len(mark)
    return end


def chunk_text(text: str, *, size: int, overlap: int) -> list[TextChunk]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("invalid chunk size/overlap")
    page_starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == PAGE_BREAK]
    has_pages = len(page_starts) > 1

    chunks: list[TextChunk] = []
    start = 0
    length = len(text)
    while start < length:
        end = length if start + size >= length else _cut(text, start, start + size)
        content = text[start:end].replace(PAGE_BREAK, "\n").strip()
        if content:
            page = bisect.bisect_right(page_starts, start) if has_pages else None
            chunks.append(TextChunk(index=len(chunks), content=content, page=page))
        if end >= length:
            break
        # Step back for overlap, but always move forward and never back across a page break.
        next_start = max(end - overlap, start + 1)
        # Ignore the separator the cut ended on; the overlap must repeat real content.
        content_end = len(text[:end].rstrip())
        page_break = text.rfind(PAGE_BREAK, next_start, end)
        line = text.find("\n", next_start, content_end)
        space = text.find(" ", next_start, min(content_end, next_start + 40))
        if page_break != -1:
            start = page_break + 1
        elif line != -1:
            start = line + 1  # overlap starts at a line, not mid-sentence
        elif space != -1:
            start = space + 1
        else:
            start = next_start
    return chunks
