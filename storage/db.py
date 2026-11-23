"""App-private SQLite persistence using WAL mode and explicit transactions."""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from config import DB_FILENAME
from engine.ranking import SearchRecord


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """Persisted document row."""

    name: str
    content: str
    detected_mode: str
    mode_override: str
    updated_at: float


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    """In-memory snapshot used for undoable Reset."""

    documents: list[StoredDocument]
    searches: list[SearchRecord]


@dataclass(frozen=True, slots=True)
class StorageResult:
    """Explicit outcome of a persistence operation."""

    ok: bool
    error: str | None = None


def resolve_app_private_db_path(custom_dir: str | Path | None = None) -> Path:
    """Return an app-private SQLite file path for Flet Android or desktop."""
    if custom_dir is not None:
        base = Path(custom_dir)
    else:
        env_dir = (
            os.environ.get("FLET_APP_STORAGE_DATA")
            or os.environ.get("ANDROID_PRIVATE")
            or os.environ.get("XDG_DATA_HOME")
        )
        base = Path(env_dir) if env_dir else (Path.home() / ".fulgur_search")
    base.mkdir(parents=True, exist_ok=True)
    return base / DB_FILENAME


class StorageManager:
    """Thread-safe SQLite manager with WAL journaling and transactional writes."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path: Path = Path(db_path) if db_path is not None else resolve_app_private_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    detected_mode TEXT NOT NULL,
                    mode_override TEXT NOT NULL DEFAULT 'auto',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS searches (
                    word TEXT PRIMARY KEY,
                    count INTEGER NOT NULL,
                    last_searched_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def load_documents(self) -> tuple[list[StoredDocument], StorageResult]:
        """Load all persisted documents in insertion order."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT name, content, detected_mode, mode_override, updated_at "
                    "FROM documents ORDER BY id ASC;"
                ).fetchall()
            docs = [
                StoredDocument(
                    name=row["name"],
                    content=row["content"],
                    detected_mode=row["detected_mode"],
                    mode_override=row["mode_override"],
                    updated_at=float(row["updated_at"]),
                )
                for row in rows
            ]
            return docs, StorageResult(ok=True)
        except sqlite3.Error as exc:
            return [], StorageResult(ok=False, error=f"Failed to load documents: {exc}")

    def load_searches(self) -> tuple[list[SearchRecord], StorageResult]:
        """Load all persisted personal search records."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT word, count, last_searched_at FROM searches "
                    "ORDER BY count DESC, last_searched_at DESC;"
                ).fetchall()
            records = [
                SearchRecord(
                    word=row["word"],
                    count=int(row["count"]),
                    last_searched_at=float(row["last_searched_at"]),
                )
                for row in rows
            ]
            return records, StorageResult(ok=True)
        except sqlite3.Error as exc:
            return [], StorageResult(ok=False, error=f"Failed to load search history: {exc}")

    def upsert_document(
        self,
        name: str,
        content: str,
        detected_mode: str,
        mode_override: str = "auto",
        now: float | None = None,
    ) -> StorageResult:
        """Insert or replace a document inside a SQLite transaction."""
        ts = time.time() if now is None else now
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO documents (name, content, detected_mode, mode_override, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        content = excluded.content,
                        detected_mode = excluded.detected_mode,
                        mode_override = excluded.mode_override,
                        updated_at = excluded.updated_at;
                    """,
                    (name, content, detected_mode, mode_override, ts, ts),
                )
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not save '{name}' to SQLite: {exc}")

    def update_document_mode(
        self,
        name: str,
        mode_override: str,
        now: float | None = None,
    ) -> StorageResult:
        """Persist user override ('auto', 'wordlist', 'prose') for a document."""
        ts = time.time() if now is None else now
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE documents SET mode_override = ?, updated_at = ? WHERE name = ?;",
                    (mode_override, ts, name),
                )
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not update mode for '{name}': {exc}")

    def delete_document(self, name: str) -> StorageResult:
        """Delete a document by name."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM documents WHERE name = ?;", (name,))
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not delete '{name}': {exc}")

    def record_search(self, word: str, now: float | None = None) -> tuple[SearchRecord | None, StorageResult]:
        """Increment search frequency and update last_searched_at transactionally."""
        ts = time.time() if now is None else now
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO searches (word, count, last_searched_at)
                    VALUES (?, 1, ?)
                    ON CONFLICT(word) DO UPDATE SET
                        count = searches.count + 1,
                        last_searched_at = excluded.last_searched_at;
                    """,
                    (word, ts),
                )
                row = conn.execute(
                    "SELECT word, count, last_searched_at FROM searches WHERE word = ?;",
                    (word,),
                ).fetchone()
            if row is None:
                return None, StorageResult(ok=False, error="Search row missing after write.")
            return (
                SearchRecord(
                    word=row["word"],
                    count=int(row["count"]),
                    last_searched_at=float(row["last_searched_at"]),
                ),
                StorageResult(ok=True),
            )
        except sqlite3.Error as exc:
            return None, StorageResult(ok=False, error=f"Could not save search '{word}': {exc}")

    def delete_search(self, word: str) -> StorageResult:
        """Remove a single search history entry."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM searches WHERE word = ?;", (word,))
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not delete '{word}': {exc}")

    def get_setting(self, key: str, default: str = "") -> str:
        """Read a persistent setting value."""
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key = ?;", (key,)).fetchone()
            return str(row["value"]) if row is not None else default
        except sqlite3.Error:
            return default

    def set_setting(self, key: str, value: str) -> StorageResult:
        """Persist a setting key/value pair."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                    """,
                    (key, value),
                )
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not save setting '{key}': {exc}")

    def create_snapshot(self) -> tuple[StorageSnapshot, StorageResult]:
        """Capture current documents and searches before an undoable reset."""
        docs, doc_res = self.load_documents()
        if not doc_res.ok:
            return StorageSnapshot([], []), doc_res
        searches, search_res = self.load_searches()
        if not search_res.ok:
            return StorageSnapshot([], []), search_res
        return StorageSnapshot(documents=docs, searches=searches), StorageResult(ok=True)

    def purge_all(self) -> StorageResult:
        """Permanently clear documents and search history."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM documents;")
                conn.execute("DELETE FROM searches;")
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not reset learned data: {exc}")

    def restore_snapshot(self, snapshot: StorageSnapshot) -> StorageResult:
        """Restore documents and searches atomically when Undo is triggered."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM documents;")
                conn.execute("DELETE FROM searches;")
                for doc in snapshot.documents:
                    conn.execute(
                        """
                        INSERT INTO documents (name, content, detected_mode, mode_override, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            doc.name,
                            doc.content,
                            doc.detected_mode,
                            doc.mode_override,
                            doc.updated_at,
                            doc.updated_at,
                        ),
                    )
                for rec in snapshot.searches:
                    conn.execute(
                        """
                        INSERT INTO searches (word, count, last_searched_at)
                        VALUES (?, ?, ?);
                        """,
                        (rec.word, rec.count, rec.last_searched_at),
                    )
            return StorageResult(ok=True)
        except sqlite3.Error as exc:
            return StorageResult(ok=False, error=f"Could not restore snapshot: {exc}")
