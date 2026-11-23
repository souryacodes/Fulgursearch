"""File decoding, binary rejection, and word-list / prose / CSV learning."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass

from config import (
    BINARY_CONTROL_RATIO,
    MAX_FILE_BYTES,
    PROSE_MAX_TERMS,
    PROSE_MIN_WORD_LEN,
    WORD_LIST_MAX_WORDS,
    WORD_LIST_RATIO,
)
from engine.sample_words import STOP_WORDS
from engine.trie import clean

PROSE_TOKEN_RE = re.compile(r"[^\W_][\w'’-]*", re.UNICODE)


class FileValidationError(ValueError):
    """Raised when a file exceeds size limits, cannot be decoded, or is binary."""


@dataclass(frozen=True, slots=True)
class LearnedFile:
    """Learned vocabulary and metadata extracted from a document."""

    detected_mode: str  # "wordlist" or "prose"
    effective_mode: str  # "wordlist" or "prose"
    terms: list[tuple[str, int]]


def _control_char_ratio(text: str) -> float:
    """Return fraction of ASCII control characters (excluding \\n, \\r, \\t)."""
    if not text:
        return 0.0
    ctrl = sum(
        1 for ch in text if (ord(ch) < 32 and ch not in ("\n", "\r", "\t")) or ord(ch) == 127
    )
    return ctrl / len(text)


def decode_file_bytes(raw: bytes) -> tuple[str, str]:
    """Decode raw bytes safely (UTF-8 BOM, UTF-16, cp1252, latin-1) or reject binary/oversized."""
    if len(raw) > MAX_FILE_BYTES:
        mb = len(raw) / (1024 * 1024)
        raise FileValidationError(f"File is too large ({mb:.1f} MB). Maximum allowed size is 5 MB.")

    if not raw:
        return "", "utf-8"

    has_utf16_bom = raw.startswith((b"\xff\xfe", b"\xfe\xff"))
    if not has_utf16_bom and b"\x00" in raw:
        raise FileValidationError("Binary files are not supported (NUL bytes detected).")

    encodings = ("utf-16",) if has_utf16_bom else ("utf-8-sig", "utf-16", "cp1252", "latin-1")
    text: str | None = None
    used_encoding = "utf-8"
    for enc in encodings:
        try:
            candidate = raw.decode(enc)
            if enc == "utf-16" and not has_utf16_bom:
                # Avoid misdecoding arbitrary 8-bit text as UTF-16 without BOM
                continue
            text = candidate
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise FileValidationError("Could not decode file as UTF-8, UTF-16, CP1252, or Latin-1.")

    # Strip any lingering BOM character if present
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    if _control_char_ratio(text) > BINARY_CONTROL_RATIO:
        raise FileValidationError("Binary files are not supported (high control-character ratio).")

    return text, used_encoding


def _non_comment_lines(text: str) -> list[str]:
    """Return stripped non-blank lines that do not start with '#'."""
    out: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(stripped)
    return out


def detect_learning_mode(text: str, filename: str) -> str:
    """Classify a file as 'wordlist' or 'prose'."""
    if filename.lower().endswith(".csv"):
        return "wordlist"
    lines = _non_comment_lines(text)
    if not lines:
        return "wordlist"
    short_lines = sum(1 for line in lines if len(line.split()) <= WORD_LIST_MAX_WORDS)
    return "wordlist" if (short_lines / len(lines)) >= WORD_LIST_RATIO else "prose"


def _learn_csv_terms(text: str) -> list[tuple[str, int]]:
    """Learn first column or 'word,rank' pairs from CSV without learning whole rows."""
    lines = _non_comment_lines(text)
    terms: list[tuple[str, int]] = []
    reader = csv.reader(io.StringIO("\n".join(lines)))
    for row in reader:
        if not row:
            continue
        word = clean(row[0])
        if not word:
            continue
        rank = 1
        if len(row) >= 2:
            second = row[1].strip()
            if second.isdigit():
                rank = max(1, int(second))
        terms.append((word, rank))
    return terms


def _learn_wordlist_terms(text: str) -> list[tuple[str, int]]:
    """Learn short lines with optional trailing ',rank' digits."""
    terms: list[tuple[str, int]] = []
    for line in _non_comment_lines(text):
        word = line
        rank = 1
        if "," in line:
            prefix, suffix = line.rsplit(",", 1)
            if prefix.strip() and suffix.strip().isdigit():
                word = prefix
                rank = max(1, int(suffix.strip()))
        cleaned = clean(word)
        if cleaned:
            terms.append((cleaned, rank))
    return terms


def _learn_prose_terms(text: str) -> list[tuple[str, int]]:
    """Extract top frequency-ranked Unicode words from prose text."""
    lines = _non_comment_lines(text)
    joined = "\n".join(lines).lower()
    counts: Counter[str] = Counter()
    for match in PROSE_TOKEN_RE.finditer(joined):
        token = match.group(0)
        if len(token) < PROSE_MIN_WORD_LEN or token in STOP_WORDS:
            continue
        counts[token] += 1
    return counts.most_common(PROSE_MAX_TERMS)


def learn_from_text(
    text: str,
    filename: str,
    mode_override: str = "auto",
) -> LearnedFile:
    """Extract learned (word, rank) pairs using auto-detection or explicit override."""
    detected = detect_learning_mode(text, filename)
    effective = detected if mode_override not in ("wordlist", "prose") else mode_override
    is_csv = filename.lower().endswith(".csv")

    if effective == "prose":
        terms = _learn_prose_terms(text)
    elif is_csv:
        terms = _learn_csv_terms(text)
    else:
        terms = _learn_wordlist_terms(text)

    return LearnedFile(
        detected_mode=detected,
        effective_mode=effective,
        terms=terms,
    )


def format_mode_label(mode: str) -> str:
    """Return the user-facing mode label ('word list' or 'prose')."""
    return "word list" if mode == "wordlist" else "prose"
