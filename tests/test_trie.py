"""Tests for engine/trie.py covering tie-breaks, trailing space, unknown prefix, duplicates, and phrases."""

from __future__ import annotations

import unittest

from engine.trie import Node, Trie, bold_prefix_len, clean


class TestTrie(unittest.TestCase):
    def test_clean_normalizes_whitespace_and_case(self) -> None:
        self.assertEqual(clean("  Apple   WATCH \t "), "apple watch")
        self.assertEqual(clean("   \n\t "), "")

    def test_node_uses_slots(self) -> None:
        node = Node()
        self.assertFalse(hasattr(node, "__dict__"))

    def test_tie_breaks_alphabetical_ascending(self) -> None:
        trie = Trie(k=5)
        for w in ("zebra", "alpha", "mango", "banana"):
            trie.add(w, 50)
        self.assertEqual(trie.suggest(" "), [])
        trie2 = Trie(k=5)
        for w in ("apricot", "apple", "apply"):
            trie2.add(w, 10)
        self.assertEqual(trie2.suggest("ap"), ["apple", "apply", "apricot"])

    def test_trailing_space_distinguishes_prefix(self) -> None:
        trie = Trie(k=5)
        trie.add("apple", 100)
        trie.add("application", 95)
        trie.add("apple watch", 85)
        trie.add("apple pie", 60)

        self.assertEqual(trie.suggest("apple"), ["apple", "apple watch", "apple pie"])
        self.assertEqual(trie.suggest("apple "), ["apple watch", "apple pie"])
        self.assertEqual(bold_prefix_len("apple"), 5)
        self.assertEqual(bold_prefix_len("apple "), 6)
        self.assertEqual(bold_prefix_len("  apple   "), 6)

    def test_unknown_prefix_returns_empty(self) -> None:
        trie = Trie(k=5)
        trie.add("python", 90)
        self.assertEqual(trie.suggest("xyz"), [])
        self.assertEqual(trie.suggest("python z"), [])

    def test_duplicate_adds_are_cumulative(self) -> None:
        trie = Trie(k=5)
        trie.add("alpha", 30)
        trie.add("alps", 50)
        self.assertEqual(trie.suggest("al"), ["alps", "alpha"])

        # Adding alpha +25 gives cumulative 55 > 50
        trie.add("alpha", 25)
        self.assertEqual(trie.scores["alpha"], 55.0)
        self.assertEqual(trie.suggest("al"), ["alpha", "alps"])

    def test_phrase_prefixes_and_top_k_slice(self) -> None:
        trie = Trie(k=3)
        phrases = [
            ("data science", 40),
            ("data structures", 90),
            ("data mining", 70),
            ("data warehouse", 60),
        ]
        for phrase, score in phrases:
            trie.add(phrase, score)
        self.assertEqual(
            trie.suggest("data "),
            ["data structures", "data mining", "data warehouse"],
        )
        self.assertEqual(bold_prefix_len("data "), 5)


if __name__ == "__main__":
    unittest.main()
