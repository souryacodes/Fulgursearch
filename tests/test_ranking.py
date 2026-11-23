"""Tests for engine/ranking.py."""

from __future__ import annotations

import unittest

from engine.ranking import (
    BASE_SCORE_CAP,
    PERSONAL_BASE_FLOOR,
    Ranker,
    SearchRecord,
    compute_personal_score,
    is_valid_history_query,
    normalize_base_score,
)


class TestRanking(unittest.TestCase):
    def test_normalized_base_never_reaches_personal_floor(self) -> None:
        self.assertLess(normalize_base_score(10_000_000.0), BASE_SCORE_CAP)
        self.assertLess(BASE_SCORE_CAP, PERSONAL_BASE_FLOOR)

    def test_personal_search_outranks_builtins_even_with_old_decay(self) -> None:
        now = 1_700_000_000.0
        old_ts = now - 365 * 86400.0  # 1 year old
        ranker = Ranker(k=5)
        # "apricot" starts at base 40 while "apple" is 100
        ranker.apply_personal_record(
            SearchRecord(word="apricot", count=1, last_searched_at=old_ts),
            now=now,
        )
        suggestions = ranker.trie.suggest("ap")
        self.assertEqual(suggestions[0], "apricot")

    def test_recency_and_frequency_ordering(self) -> None:
        now = 1_700_000_000.0
        recent = compute_personal_score(1, now - 60, now)
        older = compute_personal_score(1, now - 20 * 86400.0, now)
        frequent = compute_personal_score(3, now - 20 * 86400.0, now)
        self.assertGreater(recent, older)
        self.assertGreater(frequent, recent)

    def test_ignore_queries_under_two_chars(self) -> None:
        self.assertFalse(is_valid_history_query(""))
        self.assertFalse(is_valid_history_query("a"))
        self.assertFalse(is_valid_history_query("  z  "))
        self.assertTrue(is_valid_history_query("ab"))


if __name__ == "__main__":
    unittest.main()
