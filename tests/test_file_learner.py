"""Tests for engine/file_learner.py."""

from __future__ import annotations

import unittest

from config import MAX_FILE_BYTES
from engine.file_learner import (
    FileValidationError,
    decode_file_bytes,
    detect_learning_mode,
    learn_from_text,
)


class TestFileLearner(unittest.TestCase):
    def test_decode_utf8_strips_bom(self) -> None:
        raw = b"\xef\xbb\xbfhello world\n"
        text, enc = decode_file_bytes(raw)
        self.assertEqual(text, "hello world\n")
        self.assertEqual(enc, "utf-8-sig")

    def test_decode_utf16_and_cp1252_and_latin1(self) -> None:
        utf16_raw = "hello — world".encode("utf-16")
        text16, _ = decode_file_bytes(utf16_raw)
        self.assertEqual(text16, "hello — world")

        cp_raw = "café €".encode("cp1252")
        text_cp, _ = decode_file_bytes(cp_raw)
        self.assertIn("café", text_cp)

    def test_reject_binary_and_oversized(self) -> None:
        with self.assertRaises(FileValidationError):
            decode_file_bytes(b"abc\x00def")
        with self.assertRaises(FileValidationError):
            decode_file_bytes(b"\x01\x02\x03\x04\x05" * 20)
        with self.assertRaises(FileValidationError):
            decode_file_bytes(b"a" * (MAX_FILE_BYTES + 1))

    def test_wordlist_detection_comments_and_ranks(self) -> None:
        content = (
            "# comment line ignored\n"
            "quantum computing, 25\n"
            "rust programming,12\n"
            "docker compose\n"
            "kubernetes\n"
        )
        self.assertEqual(detect_learning_mode(content, "terms.txt"), "wordlist")
        learned = learn_from_text(content, "terms.txt")
        self.assertEqual(learned.effective_mode, "wordlist")
        terms_dict = dict(learned.terms)
        self.assertEqual(terms_dict["quantum computing"], 25)
        self.assertEqual(terms_dict["rust programming"], 12)
        self.assertEqual(terms_dict["docker compose"], 1)
        self.assertNotIn("# comment line ignored", terms_dict)

    def test_prose_detection_and_override(self) -> None:
        prose = (
            "# Header comment ignored\n"
            "Algorithms power modern search engines across mobile devices with very fast response times.\n"
            "Indexed documents enable quick lookup across local storage without any network calls.\n"
        )
        self.assertEqual(detect_learning_mode(prose, "notes.md"), "prose")
        learned = learn_from_text(prose, "notes.md")
        terms = dict(learned.terms)
        self.assertIn("algorithms", terms)
        self.assertNotIn("the", terms)
        self.assertNotIn("with", terms)
        self.assertNotIn("header", terms)

        overridden = learn_from_text(prose, "notes.md", mode_override="wordlist")
        self.assertEqual(overridden.effective_mode, "wordlist")

    def test_csv_learns_first_column_or_word_rank_never_whole_rows(self) -> None:
        csv_text = (
            "# ignored header\n"
            "nebula,40,extra metadata,ignored\n"
            "quasar,not_a_number,more text\n"
            '"solar flare",15,sun\n'
        )
        learned = learn_from_text(csv_text, "space.csv")
        self.assertEqual(learned.effective_mode, "wordlist")
        terms = dict(learned.terms)
        self.assertEqual(terms["nebula"], 40)
        self.assertEqual(terms["quasar"], 1)
        self.assertEqual(terms["solar flare"], 15)
        self.assertNotIn("extra metadata", terms)


if __name__ == "__main__":
    unittest.main()
