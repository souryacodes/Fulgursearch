"""In-document phrase matching across lines within pages with single compiled regex."""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import MAX_HITS, MIN_QUERY_CHARS_HIGHLIGHT
from engine.paginator import Page
from engine.trie import clean


@dataclass(frozen=True, slots=True)
class MatchHit:
    """Single match entry ordered by file, page, line, and character offset."""

    doc: str
    k: int
    page: int
    line: int
    text: str
    idx: int
    len: int


@dataclass(frozen=True, slots=True)
class LineSpan:
    """Highlight character range [start, end) on a single line tied to hit index k."""

    k: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Aggregated match hits, per-file counts, and per-line highlight spans."""

    query: str
    hits: list[MatchHit]
    file_counts: dict[str, int]
    total_matches: int
    is_capped: bool
    line_spans: dict[tuple[str, int, int], list[LineSpan]]  # (doc, page_no, line_no) -> spans

    @property
    def status_summary(self) -> str:
        """Return consistent match count text respecting the 300-hit render cap."""
        if self.is_capped:
            return f"{MAX_HITS}+ matches (showing first {MAX_HITS})"
        return f"{len(self.hits)} match(es)"


def compile_query_regex(
    query: str,
    match_inside_words: bool = False,
) -> re.Pattern[str] | None:
    """Compile ONE case-insensitive regex for query, or None if query < 2 chars."""
    normalized = clean(query)
    if len(normalized) < MIN_QUERY_CHARS_HIGHLIGHT:
        return None
    words = [re.escape(w) for w in normalized.split(" ") if w]
    if not words:
        return None
    body = r"\s+".join(words)
    pattern = body if match_inside_words else r"(?<![^\W_])" + body
    return re.compile(pattern, re.IGNORECASE)


def find_matches_in_docs(
    docs_pages: list[tuple[str, list[Page]]],
    query: str,
    match_inside_words: bool = False,
    max_hits: int = MAX_HITS,
) -> MatchResult:
    """Find matches across paginated documents, including phrases wrapping a line break."""
    normalized = clean(query)
    regex = compile_query_regex(normalized, match_inside_words=match_inside_words)
    if regex is None:
        return MatchResult(
            query=normalized,
            hits=[],
            file_counts={},
            total_matches=0,
            is_capped=False,
            line_spans={},
        )

    hits: list[MatchHit] = []
    file_counts: dict[str, int] = {}
    line_spans: dict[tuple[str, int, int], list[LineSpan]] = {}
    total_matches = 0
    is_capped = False

    for doc_name, pages in docs_pages:
        doc_k = 0
        for page in pages:
            lines = page.lines
            if not lines:
                continue
            page_text = "\n".join(line.text for line in lines)
            # Precompute line start/end offsets in page_text
            offsets: list[tuple[int, int]] = []
            pos = 0
            for line in lines:
                end = pos + len(line.text)
                offsets.append((pos, end))
                pos = end + 1  # +1 for '\n'

            line_idx = 0
            num_lines = len(lines)
            for match in regex.finditer(page_text):
                total_matches += 1
                file_counts[doc_name] = file_counts.get(doc_name, 0) + 1

                if len(hits) >= max_hits:
                    is_capped = True
                    continue

                m_start, m_end = match.start(), match.end()
                while line_idx < num_lines - 1 and offsets[line_idx][1] < m_start:
                    line_idx += 1

                start_off, start_end = offsets[line_idx]
                start_line = lines[line_idx]
                rel_start = max(0, m_start - start_off)
                first_line_len = min(m_end, start_end) - m_start

                # Build snippet text (join wrapped lines with a space if match crosses newline)
                snippet_text = start_line.text
                if m_end > start_end and line_idx + 1 < num_lines:
                    # Include continuation lines so snippet shows the wrapped phrase clearly
                    extra_parts = [start_line.text]
                    scan = line_idx + 1
                    while scan < num_lines and offsets[scan][0] < m_end:
                        extra_parts.append(lines[scan].text)
                        scan += 1
                    snippet_text = " ".join(extra_parts)
                    hit_len = len(match.group(0))
                else:
                    hit_len = max(1, first_line_len)

                hits.append(
                    MatchHit(
                        doc=doc_name,
                        k=doc_k,
                        page=page.number,
                        line=start_line.number,
                        text=snippet_text,
                        idx=rel_start,
                        len=hit_len,
                    )
                )

                # Record per-line highlight spans for every line overlapped by [m_start, m_end)
                span_line = line_idx
                while span_line < num_lines:
                    l_start, l_end = offsets[span_line]
                    if l_start >= m_end:
                        break
                    seg_start = max(0, m_start - l_start)
                    seg_end = min(l_end - l_start, m_end - l_start)
                    if seg_end > seg_start:
                        key = (doc_name, page.number, lines[span_line].number)
                        line_spans.setdefault(key, []).append(
                            LineSpan(k=doc_k, start=seg_start, end=seg_end)
                        )
                    span_line += 1

                doc_k += 1

    return MatchResult(
        query=normalized,
        hits=hits,
        file_counts=file_counts,
        total_matches=total_matches,
        is_capped=is_capped,
        line_spans=line_spans,
    )
