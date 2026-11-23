"""Bounded base normalization and recency-decayed personal search ranking."""

from __future__ import annotations

import time
from dataclasses import dataclass

from config import (
    BASE_NORM_SCALE,
    BASE_SCORE_CAP,
    MIN_QUERY_CHARS_HISTORY,
    PERSONAL_BASE_FLOOR,
    PERSONAL_DECAY_HALF_LIFE_DAYS,
    PERSONAL_FREQ_WEIGHT,
    TOP_K,
)
from engine.sample_words import SAMPLE_WORDS
from engine.trie import Trie, clean


@dataclass(frozen=True, slots=True)
class SearchRecord:
    """Persisted user search frequency and last timestamp."""

    word: str
    count: int
    last_searched_at: float


def is_valid_history_query(text: str) -> bool:
    """Return True if the normalized query meets the minimum length (>= 2 chars)."""
    return len(clean(text)) >= MIN_QUERY_CHARS_HISTORY


def normalize_base_score(raw_score: float) -> float:
    """Monotonically map any positive raw score strictly below BASE_SCORE_CAP."""
    if raw_score <= 0.0:
        return 0.0
    return BASE_SCORE_CAP * (raw_score / (raw_score + BASE_NORM_SCALE))


def recency_decay(last_searched_at: float, now: float) -> float:
    """Compute half-life recency multiplier in [0.5, 1.0]."""
    age_seconds = max(0.0, now - last_searched_at)
    age_days = age_seconds / 86400.0
    decay = 0.5 ** (age_days / PERSONAL_DECAY_HALF_LIFE_DAYS)
    return 0.5 + 0.5 * decay


def compute_personal_score(count: int, last_searched_at: float, now: float) -> float:
    """Compute personal search score strictly above any normalized base score."""
    if count <= 0:
        return 0.0
    return PERSONAL_BASE_FLOOR + count * PERSONAL_FREQ_WEIGHT * recency_decay(
        last_searched_at, now
    )


class Ranker:
    """Maintains raw base weights + personal history and feeds an incremental Trie."""

    def __init__(self, k: int = TOP_K) -> None:
        self.k: int = k
        self.raw_base: dict[str, float] = {}
        self.norm_base: dict[str, float] = {}
        self.personal_scores: dict[str, float] = {}
        self.trie: Trie = Trie(k=k)
        self.load_sample_words()

    def load_sample_words(self) -> None:
        """Seed the ranker and trie with built-in SAMPLE_WORDS."""
        for word, rank in SAMPLE_WORDS:
            self.add_base_term(word, float(rank))

    def add_base_term(self, word: str, raw_weight: float) -> None:
        """Accumulate raw base score for word and apply normalized delta to trie."""
        cleaned = clean(word)
        if not cleaned or raw_weight <= 0.0:
            return
        new_raw = self.raw_base.get(cleaned, 0.0) + float(raw_weight)
        self.raw_base[cleaned] = new_raw
        old_norm = self.norm_base.get(cleaned, 0.0)
        new_norm = normalize_base_score(new_raw)
        self.norm_base[cleaned] = new_norm
        delta = new_norm - old_norm
        if delta != 0.0:
            self.trie.add(cleaned, delta)

    def apply_document_terms(self, terms: list[tuple[str, int]]) -> None:
        """Incrementally add a document's learned (word, rank) pairs into the trie."""
        for word, rank in terms:
            self.add_base_term(word, float(rank))

    def apply_personal_record(self, record: SearchRecord, now: float | None = None) -> None:
        """Apply or update a personal search record in the trie."""
        cleaned = clean(record.word)
        if not is_valid_history_query(cleaned):
            return
        ts = time.time() if now is None else now
        old_personal = self.personal_scores.get(cleaned, 0.0)
        new_personal = compute_personal_score(record.count, record.last_searched_at, ts)
        self.personal_scores[cleaned] = new_personal
        delta = new_personal - old_personal
        if delta != 0.0:
            self.trie.add(cleaned, delta)

    @classmethod
    def rebuild(
        cls,
        doc_terms_list: list[list[tuple[str, int]]],
        records: list[SearchRecord],
        now: float | None = None,
        k: int = TOP_K,
    ) -> "Ranker":
        """Build a fresh Ranker from sample words, learned docs, and personal searches."""
        ranker = cls(k=k)
        for terms in doc_terms_list:
            ranker.apply_document_terms(terms)
        ts = time.time() if now is None else now
        for rec in records:
            ranker.apply_personal_record(rec, now=ts)
        return ranker
