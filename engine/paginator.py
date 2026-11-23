"""Deterministic line-and-character pagination for document viewing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import PAGE_CHARS, PAGE_LINES

LINE_SPLIT_RE = re.compile(r"\r?\n")


@dataclass(frozen=True, slots=True)
class PageLine:
    """Single 1-based global line within a paginated document."""

    number: int
    text: str


@dataclass(frozen=True, slots=True)
class Page:
    """One viewer page containing 1-based PageLine entries."""

    number: int  # 1-based page number
    lines: tuple[PageLine, ...]


def paginate_text(
    text: str,
    max_lines: int = PAGE_LINES,
    max_chars: int = PAGE_CHARS,
) -> list[Page]:
    """Split text into pages ending at max_lines OR accumulated chars >= max_chars."""
    raw_lines = LINE_SPLIT_RE.split(text)
    pages: list[Page] = []
    current_lines: list[PageLine] = []
    char_count = 0

    for idx, line_text in enumerate(raw_lines, start=1):
        current_lines.append(PageLine(number=idx, text=line_text))
        char_count += len(line_text)
        if len(current_lines) >= max_lines or char_count >= max_chars:
            pages.append(Page(number=len(pages) + 1, lines=tuple(current_lines)))
            current_lines = []
            char_count = 0

    if current_lines:
        pages.append(Page(number=len(pages) + 1, lines=tuple(current_lines)))

    if not pages:
        pages.append(Page(number=1, lines=(PageLine(number=1, text=""),)))

    return pages
