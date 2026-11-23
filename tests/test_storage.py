"""Tests for storage/db.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.db import StorageManager


class TestStorage(unittest.TestCase):
    def test_persistence_across_reopen_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = StorageManager(db_path=db_path)

            res_doc = store.upsert_document("a.txt", "hello world", "prose", "auto", now=100.0)
            self.assertTrue(res_doc.ok)

            rec, res_search = store.record_search("hello", now=200.0)
            self.assertTrue(res_search.ok)
            self.assertIsNotNone(rec)
            self.assertEqual(rec.count, 1)  # type: ignore[union-attr]

            # Reopen fresh manager instance simulating app restart
            reopened = StorageManager(db_path=db_path)
            docs, _ = reopened.load_documents()
            searches, _ = reopened.load_searches()
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].name, "a.txt")
            self.assertEqual(len(searches), 1)
            self.assertEqual(searches[0].word, "hello")

            # Individual search deletion
            self.assertTrue(reopened.delete_search("hello").ok)
            searches_after, _ = reopened.load_searches()
            self.assertEqual(searches_after, [])

    def test_snapshot_undo_and_purge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = StorageManager(db_path=db_path)
            store.upsert_document("notes.txt", "python trie", "wordlist", "auto", now=10.0)
            store.record_search("trie", now=20.0)

            snap, snap_res = store.create_snapshot()
            self.assertTrue(snap_res.ok)
            self.assertTrue(store.purge_all().ok)
            self.assertEqual(store.load_documents()[0], [])
            self.assertEqual(store.load_searches()[0], [])

            self.assertTrue(store.restore_snapshot(snap).ok)
            self.assertEqual(len(store.load_documents()[0]), 1)
            self.assertEqual(len(store.load_searches()[0]), 1)


if __name__ == "__main__":
    unittest.main()
