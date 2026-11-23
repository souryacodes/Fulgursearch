"""Background worker thread for file decoding, learning, pagination, and matching."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config import TOP_K
from engine.file_learner import (
    FileValidationError,
    decode_file_bytes,
    learn_from_text,
)
from engine.matcher import MatchResult, find_matches_in_docs
from engine.paginator import Page, paginate_text
from engine.ranking import Ranker, SearchRecord
from storage.db import StorageManager, StoredDocument


@dataclass(slots=True)
class DocumentState:
    """In-memory indexed and paginated representation of a loaded document."""

    name: str
    text: str
    detected_mode: str
    mode_override: str
    effective_mode: str
    pages: list[Page]
    terms: list[tuple[str, int]]


@dataclass(frozen=True, slots=True)
class PendingFileInput:
    """Raw file bytes and desired target name ready for background ingestion."""

    target_name: str
    raw_bytes: bytes | None = None
    file_path: str | None = None


@dataclass(frozen=True, slots=True)
class StateUpdatedEvent:
    """Delivered to the UI via result_queue whenever documents or trie change."""

    docs: list[DocumentState]
    ranker: Ranker
    searches: list[SearchRecord]
    added_count: int
    errors: list[str]
    storage_error: str | None
    refresh_query: bool = False


@dataclass(frozen=True, slots=True)
class MatchCompletedEvent:
    """Delivered to the UI via result_queue when background regex matching finishes."""

    result: MatchResult
    generation: int


WorkerEvent = StateUpdatedEvent | MatchCompletedEvent


class BackgroundIndexer:
    """Single-worker queue processor for indexing, pagination, and document search."""

    def __init__(
        self,
        storage: StorageManager,
        on_event_ready: Callable[[], None] | None = None,
    ) -> None:
        self.storage: StorageManager = storage
        self.on_event_ready: Callable[[], None] | None = on_event_ready
        self.task_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.result_queue: queue.Queue[WorkerEvent] = queue.Queue()

        self._docs: list[DocumentState] = []
        self._searches: list[SearchRecord] = []
        self._ranker: Ranker = Ranker(k=TOP_K)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="fulgur-indexer",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the worker thread to exit cleanly."""
        self._stop_event.set()
        self.task_queue.put(("shutdown", None))
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def submit_load_initial(self) -> None:
        """Queue initial load of persisted documents and searches."""
        self.task_queue.put(("load_initial", None))

    def submit_ingest_files(self, files: list[PendingFileInput]) -> None:
        """Queue decoding, learning, pagination, and SQLite persistence for files."""
        self.task_queue.put(("ingest_files", files))

    def submit_toggle_mode(self, doc_name: str, new_mode_override: str) -> None:
        """Queue re-learning a single document under a new mode override."""
        self.task_queue.put(("toggle_mode", (doc_name, new_mode_override)))

    def submit_remove_doc(self, doc_name: str) -> None:
        """Queue removing a document from SQLite and refreshing the trie."""
        self.task_queue.put(("remove_doc", doc_name))

    def submit_rebuild_from_storage(self) -> None:
        """Queue full reload from SQLite (e.g. after undo restore or purge)."""
        self.task_queue.put(("load_initial", None))

    def submit_match(
        self,
        docs_snapshot: list[tuple[str, list[Page]]],
        query: str,
        match_inside_words: bool,
        generation: int,
    ) -> None:
        """Queue background regex matching across paginated documents."""
        self.task_queue.put(
            ("match", (docs_snapshot, query, match_inside_words, generation))
        )

    def drain_events(self) -> list[WorkerEvent]:
        """Drain all queued worker events without blocking."""
        events: list[WorkerEvent] = []
        while True:
            try:
                events.append(self.result_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _emit(self, event: WorkerEvent) -> None:
        self.result_queue.put(event)
        if self.on_event_ready is not None:
            self.on_event_ready()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                kind, payload = self.task_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if kind == "shutdown":
                break
            if kind == "load_initial":
                self._handle_load_initial()
            elif kind == "ingest_files":
                self._handle_ingest_files(payload)  # type: ignore[arg-type]
            elif kind == "toggle_mode":
                doc_name, mode_override = payload  # type: ignore[misc]
                self._handle_toggle_mode(doc_name, mode_override)
            elif kind == "remove_doc":
                self._handle_remove_doc(payload)  # type: ignore[arg-type]
            elif kind == "match":
                docs_snap, query, inside, gen = payload  # type: ignore[misc]
                self._handle_match(docs_snap, query, inside, gen)

    def _doc_from_stored(self, stored: StoredDocument) -> DocumentState:
        learned = learn_from_text(
            stored.content,
            stored.name,
            mode_override=stored.mode_override,
        )
        pages = paginate_text(stored.content)
        return DocumentState(
            name=stored.name,
            text=stored.content,
            detected_mode=learned.detected_mode,
            mode_override=stored.mode_override,
            effective_mode=learned.effective_mode,
            pages=pages,
            terms=learned.terms,
        )

    def _handle_load_initial(self) -> None:
        stored_docs, doc_res = self.storage.load_documents()
        searches, search_res = self.storage.load_searches()
        err = doc_res.error or search_res.error

        # Incremental per-document trie construction
        ranker = Ranker(k=TOP_K)
        docs: list[DocumentState] = []
        for sdoc in stored_docs:
            state = self._doc_from_stored(sdoc)
            docs.append(state)
            ranker.apply_document_terms(state.terms)

        now = time.time()
        for rec in searches:
            ranker.apply_personal_record(rec, now=now)

        self._docs = docs
        self._searches = searches
        self._ranker = ranker

        self._emit(
            StateUpdatedEvent(
                docs=list(self._docs),
                ranker=self._ranker,
                searches=list(self._searches),
                added_count=0,
                errors=[],
                storage_error=err,
                refresh_query=False,
            )
        )

    def _handle_ingest_files(self, files: list[PendingFileInput]) -> None:
        errors: list[str] = []
        storage_errors: list[str] = []
        added_count = 0
        replaced_any = False
        incremental_terms: list[list[tuple[str, int]]] = []

        for item in files:
            try:
                raw = item.raw_bytes
                if raw is None and item.file_path:
                    raw = Path(item.file_path).read_bytes()
                if raw is None:
                    errors.append(f"{item.target_name}: could not read file bytes.")
                    continue

                text, _enc = decode_file_bytes(raw)
                learned = learn_from_text(text, item.target_name, mode_override="auto")
                pages = paginate_text(text)

                save_res = self.storage.upsert_document(
                    name=item.target_name,
                    content=text,
                    detected_mode=learned.detected_mode,
                    mode_override="auto",
                )
                if not save_res.ok:
                    storage_errors.append(save_res.error or f"Failed to save {item.target_name}")
                    continue

                new_doc = DocumentState(
                    name=item.target_name,
                    text=text,
                    detected_mode=learned.detected_mode,
                    mode_override="auto",
                    effective_mode=learned.effective_mode,
                    pages=pages,
                    terms=learned.terms,
                )

                existing_idx = next(
                    (i for i, d in enumerate(self._docs) if d.name == item.target_name),
                    -1,
                )
                if existing_idx >= 0:
                    self._docs[existing_idx] = new_doc
                    replaced_any = True
                else:
                    self._docs.append(new_doc)
                    incremental_terms.append(new_doc.terms)

                added_count += 1
            except FileValidationError as exc:
                errors.append(f"{item.target_name}: {exc}")
            except OSError as exc:
                errors.append(f"{item.target_name}: read error ({exc}).")

        searches, search_res = self.storage.load_searches()
        if not search_res.ok and search_res.error:
            storage_errors.append(search_res.error)
        self._searches = searches

        if replaced_any:
            self._ranker = Ranker.rebuild(
                [d.terms for d in self._docs],
                self._searches,
                now=time.time(),
                k=TOP_K,
            )
        else:
            # Update the trie incrementally per newly added document
            next_ranker = Ranker.rebuild(
                [d.terms for d in self._docs[:-len(incremental_terms)] if incremental_terms]
                if False
                else [d.terms for d in self._docs],
                self._searches,
                now=time.time(),
                k=TOP_K,
            ) if False else self._clone_and_apply_incremental(incremental_terms)
            self._ranker = next_ranker

        self._emit(
            StateUpdatedEvent(
                docs=list(self._docs),
                ranker=self._ranker,
                searches=list(self._searches),
                added_count=added_count,
                errors=errors,
                storage_error="; ".join(storage_errors) if storage_errors else None,
                refresh_query=added_count > 0,
            )
        )

    def _clone_and_apply_incremental(
        self,
        new_terms_per_doc: list[list[tuple[str, int]]],
    ) -> Ranker:
        """Apply incremental document terms onto a fresh Trie snapshot without re-parsing old docs."""
        if not new_terms_per_doc:
            return self._ranker
        # Build from cached terms + apply new docs incrementally so UI thread never sees a mutating Trie
        prior_count = len(self._docs) - len(new_terms_per_doc)
        ranker = Ranker(k=TOP_K)
        for doc in self._docs[:prior_count]:
            ranker.apply_document_terms(doc.terms)
        for terms in new_terms_per_doc:
            ranker.apply_document_terms(terms)
        now = time.time()
        for rec in self._searches:
            ranker.apply_personal_record(rec, now=now)
        return ranker

    def _handle_toggle_mode(self, doc_name: str, new_mode_override: str) -> None:
        save_res = self.storage.update_document_mode(doc_name, new_mode_override)
        storage_error = save_res.error if not save_res.ok else None

        if save_res.ok:
            for idx, doc in enumerate(self._docs):
                if doc.name == doc_name:
                    learned = learn_from_text(
                        doc.text,
                        doc.name,
                        mode_override=new_mode_override,
                    )
                    self._docs[idx] = DocumentState(
                        name=doc.name,
                        text=doc.text,
                        detected_mode=learned.detected_mode,
                        mode_override=new_mode_override,
                        effective_mode=learned.effective_mode,
                        pages=doc.pages,
                        terms=learned.terms,
                    )
                    break

        searches, _ = self.storage.load_searches()
        self._searches = searches
        self._ranker = Ranker.rebuild(
            [d.terms for d in self._docs],
            self._searches,
            now=time.time(),
            k=TOP_K,
        )

        self._emit(
            StateUpdatedEvent(
                docs=list(self._docs),
                ranker=self._ranker,
                searches=list(self._searches),
                added_count=0,
                errors=[],
                storage_error=storage_error,
                refresh_query=False,
            )
        )

    def _handle_remove_doc(self, doc_name: str) -> None:
        del_res = self.storage.delete_document(doc_name)
        storage_error = del_res.error if not del_res.ok else None
        if del_res.ok:
            self._docs = [d for d in self._docs if d.name != doc_name]

        searches, _ = self.storage.load_searches()
        self._searches = searches
        self._ranker = Ranker.rebuild(
            [d.terms for d in self._docs],
            self._searches,
            now=time.time(),
            k=TOP_K,
        )

        self._emit(
            StateUpdatedEvent(
                docs=list(self._docs),
                ranker=self._ranker,
                searches=list(self._searches),
                added_count=0,
                errors=[],
                storage_error=storage_error,
                refresh_query=True,
            )
        )

    def _handle_match(
        self,
        docs_snapshot: list[tuple[str, list[Page]]],
        query: str,
        match_inside_words: bool,
        generation: int,
    ) -> None:
        result = find_matches_in_docs(
            docs_snapshot,
            query=query,
            match_inside_words=match_inside_words,
        )
        self._emit(MatchCompletedEvent(result=result, generation=generation))
