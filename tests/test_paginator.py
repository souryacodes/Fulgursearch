"""Tests for engine/paginator.py."""

from __future__ import annotations

import unittest

from engine.paginator import paginate_text


class TestPaginator(unittest.TestCase):
    def test_empty_file_gives_one_empty_page(self) -> None:
        pages = paginate_text("")
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].number, 1)
        self.assertEqual(len(pages[0].lines), 1)
        self.assertEqual(pages[0].lines[0].number, 1)
        self.assertEqual(pages[0].lines[0].text, "")

    def test_page_splits_at_40_lines_with_global_line_numbers(self) -> None:
        text = "\n".join(f"line {i}" for i in range(1, 86))
        pages = paginate_text(text)
        self.assertEqual(len(pages), 3)
        self.assertEqual(len(pages[0].lines), 40)
        self.assertEqual(len(pages[1].lines), 40)
        self.assertEqual(len(pages[2].lines), 5)
        self.assertEqual(pages[1].lines[0].number, 41)
        self.assertEqual(pages[2].lines[-1].number, 85)

    def test_page_splits_at_2600_chars(self) -> None:
        line = "x" * 900
        text = "\n".join([line, line, line, line])  # 3rd line reaches 2700 >= 2600
        pages = paginate_text(text)
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(pages[0].lines), 3)
        self.assertEqual(len(pages[1].lines), 1)
        self.assertEqual(pages[1].lines[0].number, 4)


if __name__ == "__main__":
    unittest.main()
