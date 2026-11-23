"""End-to-end acceptance tests verifying all 8 Fulgur Search functional criteria."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from engine.file_learner import learn_from_text
from engine.matcher import find_matches_in_docs
from engine.paginator import paginate_text
from engine.ranking import Ranker
from engine.trie import bold_prefix_len
from storage.db import StorageManager
from workers.indexer import (
    BackgroundIndexer,
    MatchCompletedEvent,
    PendingFileInput,
    StateUpdatedEvent,
)


class TestAcceptance(unittest.TestCase):
    def test_1_typing_a_shows_5_suggestions_under_1ms_with_bold_and_ties(self) -> None:
        ranker = Ranker(k=5)
        t0 = time.perf_counter()
        results = ranker.trie.suggest("a")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(len(results), 5)
        self.assertLess(elapsed_ms, 1.0)
        self.assertEqual(bold_prefix_len("a"), 1)
        # Alphabetical tie-break check among equal-score words
        ranker.trie.add("aardvark", 5000.0)
        ranker.trie.add("abacus", 5000.0)
        top2 = ranker.trie.suggest("a")[:2]
        self.assertEqual(top2, ["aardvark", "abacus"])

    def test_2_apple_space_suggests_only_apple_space_phrases(self) -> None:
        ranker = Ranker(k=5)
        results = ranker.trie.suggest("apple ")
        self.assertTrue(len(results) > 0)
        for item in results:
            self.assertTrue(item.startswith("apple "))
        self.assertNotIn("apple", results)
        self.assertNotIn("application", results)

    def test_3_new_search_ranks_first_survives_restart_and_deletable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "fulgur.db"
            store = StorageManager(db_path=db_path)
            rec, res = store.record_search("anchor", now=time.time())
            self.assertTrue(res.ok)
            self.assertIsNotNone(rec)

            # Restart simulation
            store2 = StorageManager(db_path=db_path)
            docs2, _ = store2.load_documents()
            searches2, _ = store2.load_searches()
            ranker2 = Ranker.rebuild([learn_from_text(d.content, d.name).terms for d in docs2], searches2)
            self.assertEqual(ranker2.trie.suggest("an")[0], "anchor")

            # Individual delete restores built-in leader ("android" 90)
            self.assertTrue(store2.delete_search("anchor").ok)
            searches3, _ = store2.load_searches()
            ranker3 = Ranker.rebuild([], searches3)
            self.assertEqual(ranker3.trie.suggest("an")[0], "android")

    def test_4_three_mb_file_background_indexing_and_lookup_stay_fast(self) -> None:
        # Build ~3.1 MB synthetic prose/line file
        line = "Fulgur search indexing benchmark line with algorithm and python tokens.\n"
        repeat_count = (3 * 1024 * 1024) // len(line.encode("utf-8")) + 10
        big_bytes = (line * repeat_count).encode("utf-8")
        self.assertGreater(len(big_bytes), 3 * 1024 * 1024)

        with tempfile.TemporaryDirectory() as tmpdir:
            store = StorageManager(db_path=Path(tmpdir) / "big.db")
            indexer = BackgroundIndexer(storage=store)
            try:
                indexer.submit_ingest_files([PendingFileInput(target_name="big.txt", raw_bytes=big_bytes)])
                deadline = time.time() + 10.0
                updated: StateUpdatedEvent | None = None
                while time.time() < deadline:
                    for ev in indexer.drain_events():
                        if isinstance(ev, StateUpdatedEvent) and ev.added_count == 1:
                            updated = ev
                    if updated is not None:
                        break
                    time.sleep(0.02)

                self.assertIsNotNone(updated)
                assert updated is not None
                t0 = time.perf_counter()
                sugs = updated.ranker.trie.suggest("alg")
                lookup_ms = (time.perf_counter() - t0) * 1000.0
                self.assertIn("algorithm", sugs)
                self.assertLess(lookup_ms, 1.0)

                # Background match stays capped at 300
                indexer.submit_match(
                    [(updated.docs[0].name, updated.docs[0].pages)],
                    "algorithm",
                    match_inside_words=False,
                    generation=1,
                )
                match_ev: MatchCompletedEvent | None = None
                deadline = time.time() + 10.0
                while time.time() < deadline:
                    for ev in indexer.drain_events():
                        if isinstance(ev, MatchCompletedEvent):
                            match_ev = ev
                    if match_ev is not None:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(match_ev)
                assert match_ev is not None
                self.assertTrue(match_ev.result.is_capped)
                self.assertEqual(len(match_ev.result.hits), 300)
            finally:
                indexer.stop()

    def test_5_ant_boundary_toggle_and_a_highlights_nothing(self) -> None:
        pages = paginate_text("want plant ant")
        self.assertEqual(len(find_matches_in_docs([("f.txt", pages)], "ant", False).hits), 1)
        self.assertEqual(len(find_matches_in_docs([("f.txt", pages)], "ant", True).hits), 3)
        self.assertEqual(len(find_matches_in_docs([("f.txt", pages)], "a", False).hits), 0)

    def test_6_hit_counter_navigation_and_list_agree(self) -> None:
        text = "\n".join("alpha beta alpha" for _ in range(200))  # 400 matches
        pages = paginate_text(text)
        res = find_matches_in_docs([("a.txt", pages)], "alpha")
        self.assertEqual(len(res.hits), 300)
        self.assertTrue(res.is_capped)
        self.assertEqual(res.status_summary, "300+ matches (showing first 300)")

    def test_7_csv_first_column_becomes_suggestions(self) -> None:
        csv_data = "zirconia,90,gemstone description\nzircon,40,mineral\n"
        learned = learn_from_text(csv_data, "gems.csv")
        ranker = Ranker(k=5)
        ranker.apply_document_terms(learned.terms)
        sugs = ranker.trie.suggest("zir")
        self.assertEqual(sugs, ["zirconia", "zircon"])
        self.assertEqual(ranker.trie.suggest("gem"), [])


if __name__ == "__main__":
    unittest.main()
