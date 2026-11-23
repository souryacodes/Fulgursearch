"""Tests for engine/matcher.py."""

from __future__ import annotations

import unittest

from engine.matcher import find_matches_in_docs
from engine.paginator import paginate_text


class TestMatcher(unittest.TestCase):
    def test_word_boundary_default_vs_match_inside_words(self) -> None:
        text = "An ant carried a plant while I want another ant."
        pages = paginate_text(text)

        res_default = find_matches_in_docs([("doc.txt", pages)], "ant", match_inside_words=False)
        self.assertEqual(len(res_default.hits), 2)
        self.assertEqual(res_default.file_counts["doc.txt"], 2)

        res_inside = find_matches_in_docs([("doc.txt", pages)], "ant", match_inside_words=True)
        self.assertEqual(len(res_inside.hits), 4)  # ant, plant, want, ant

    def test_minimum_two_chars_to_highlight(self) -> None:
        pages = paginate_text("a cat and a bat")
        res = find_matches_in_docs([("doc.txt", pages)], "a")
        self.assertEqual(res.hits, [])
        self.assertEqual(res.total_matches, 0)

    def test_phrase_wrapping_across_line_break_within_same_page(self) -> None:
        text = "Learning python\ntutorial basics today"
        pages = paginate_text(text)
        res = find_matches_in_docs([("notes.txt", pages)], "python tutorial")
        self.assertEqual(len(res.hits), 1)
        self.assertEqual(res.hits[0].page, 1)
        self.assertEqual(res.hits[0].line, 1)
        # Both lines should have highlight spans sharing hit k=0
        self.assertIn(("notes.txt", 1, 1), res.line_spans)
        self.assertIn(("notes.txt", 1, 2), res.line_spans)
        self.assertEqual(res.line_spans[("notes.txt", 1, 1)][0].k, 0)
        self.assertEqual(res.line_spans[("notes.txt", 1, 2)][0].k, 0)

    def test_hit_cap_300_agrees_with_counter(self) -> None:
        text = "\n".join("apple banana apple" for _ in range(250))  # 500 matches
        pages = paginate_text(text)
        res = find_matches_in_docs([("many.txt", pages)], "apple")
        self.assertTrue(res.is_capped)
        self.assertEqual(len(res.hits), 300)
        self.assertEqual(res.total_matches, 500)
        self.assertEqual(res.status_summary, "300+ matches (showing first 300)")


if __name__ == "__main__":
    unittest.main()
