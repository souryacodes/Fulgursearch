"""Main Flet application controller wiring search, suggestions, viewer, storage, and worker."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import flet as ft

from config import (
    ALLOWED_EXTENSIONS,
    APP_NAME,
    MIN_QUERY_CHARS_HISTORY,
    RESET_UNDO_SECONDS,
    TOP_K,
)
from engine.matcher import MatchResult
from engine.ranking import Ranker, SearchRecord, is_valid_history_query
from engine.trie import clean
from storage.db import StorageManager, StorageSnapshot
from theme import MAX_CONTENT_WIDTH, RADIUS_CARD, ThemePalette, get_palette
from ui.dialogs import build_confirm_dialog, build_duplicate_file_dialog
from ui.history_section import HistorySection
from ui.search_bar import SearchHeader
from ui.suggestions import SuggestionsCard
from ui.viewer import DocumentViewer
from workers.indexer import (
    BackgroundIndexer,
    DocumentState,
    MatchCompletedEvent,
    PendingFileInput,
    StateUpdatedEvent,
)


def _unique_copy_name(filename: str, existing_names: set[str]) -> str:
    """Generate a non-conflicting filename like 'notes (2).txt'."""
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = f"{stem} ({counter}){suffix}"
        if candidate not in existing_names:
            return candidate
        counter += 1


class FulgurSearchApp:
    """Top-level Fulgur Search coordinator attached to a Flet Page."""

    def __init__(self, page: ft.Page, storage: StorageManager | None = None) -> None:
        self.page = page
        self.storage = storage or StorageManager()
        self.palette: ThemePalette = self._resolve_palette()

        # Runtime state
        self.docs: list[DocumentState] = []
        self.searches: list[SearchRecord] = []
        self.ranker: Ranker = Ranker(k=TOP_K)
        self.active_doc_name: str | None = None
        self.active_query: str = ""
        self.match_result: MatchResult | None = None
        self.current_hit_index: int = -1
        self.match_inside_words: bool = self.storage.get_setting("match_inside_words", "0") == "1"
        self.reduce_animations: bool = self._detect_reduce_animations()

        self.current_raw_input: str = ""
        self.current_suggestions: list[str] = []
        self.active_suggestion_index: int = -1
        self._match_generation: int = 0
        self._last_searched_count: int = 0
        self._last_search_saved: bool = True

        # Reset-undo state
        self._pending_reset_snapshot: StorageSnapshot | None = None
        self._reset_purge_timer: threading.Timer | None = None

        # Duplicate resolution queue
        self._pending_raw_files: list[PendingFileInput] = []
        self._resolved_files: list[PendingFileInput] = []
        self._active_dialog: ft.AlertDialog | None = None

        self._configure_page()
        self._build_ui()

        self.indexer = BackgroundIndexer(
            storage=self.storage,
            on_event_ready=self._notify_worker_event,
        )
        self.viewer.set_loading_files(True)
        self.indexer.submit_load_initial()
        self.page.update()

    def _detect_reduce_animations(self) -> bool:
        saved = self.storage.get_setting("reduce_animations", "")
        if saved in ("0", "1"):
            return saved == "1"
        media = getattr(self.page, "media", None)
        if media is not None and getattr(media, "disable_animations", False):
            return True
        return False

    def _resolve_palette(self) -> ThemePalette:
        brightness = getattr(self.page, "platform_brightness", None)
        is_dark = brightness == ft.Brightness.DARK
        return get_palette(is_dark)

    def _configure_page(self) -> None:
        self.page.title = APP_NAME
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.bgcolor = self.palette.bg
        self.page.padding = 0
        self.page.theme = ft.Theme(
            color_scheme_seed=self.palette.primary,
            use_material3=True,
        )
        self.page.on_keyboard_event = self._on_keyboard_event
        self.page.on_platform_brightness_change = self._on_brightness_change
        self.page.on_resize = self._on_resize
        self.page.on_view_pop = self._on_view_pop
        self.page.on_close = self._on_page_close

    def _build_ui(self) -> None:
        self.file_picker = ft.FilePicker(on_result=self._on_files_picked)
        self.page.overlay.append(self.file_picker)

        self.warning_text = ft.Text("", size=14, color=self.palette.warning_text, expand=True)
        self.warning_banner = ft.Container(
            visible=False,
            bgcolor=self.palette.warning_bg,
            border=ft.Border.all(1, self.palette.warning_border),
            border_radius=RADIUS_CARD,
            padding=12,
            margin=ft.Margin(0, 0, 0, 14),
            content=ft.Semantics(
                live_region=True,
                content=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=self.palette.warning_border, size=20),
                        self.warning_text,
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=18,
                            icon_color=self.palette.warning_text,
                            tooltip="Dismiss warning",
                            on_click=lambda _: self._dismiss_warning(),
                        ),
                    ],
                ),
            ),
        )

        self.search_header = SearchHeader(
            palette=self.palette,
            on_query_change=self._on_query_change,
            on_submit_search=self.do_search,
        )
        self.suggestions_card = SuggestionsCard(
            palette=self.palette,
            on_select=self._on_suggestion_selected,
            on_complete=self._on_suggestion_completed,
        )
        self.viewer = DocumentViewer(
            palette=self.palette,
            on_add_files=self._trigger_file_picker,
            on_select_tab=self._on_select_tab,
            on_request_remove_doc=self._confirm_remove_doc,
            on_toggle_learn_mode=self._on_toggle_learn_mode,
            on_toggle_inside_words=self._on_toggle_inside_words,
            on_prev_hit=lambda: self._show_hit(self.current_hit_index - 1),
            on_next_hit=lambda: self._show_hit(self.current_hit_index + 1),
            on_clear_highlight=self.clear_highlight,
            on_select_hit=self._show_hit,
        )
        self.history_section = HistorySection(
            palette=self.palette,
            on_reset_clicked=self._confirm_reset,
            on_delete_search=self._delete_search_entry,
            on_toggle_reduce_animations=self._on_toggle_reduce_animations,
        )

        self.main_column = ft.Column(
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self.warning_banner,
                self.search_header,
                self.suggestions_card,
                self.search_header.result_card,
                ft.Container(key="viewer-anchor", content=self.viewer),
                self.history_section,
            ],
        )

        self.centered_box = ft.Container(
            width=MAX_CONTENT_WIDTH,
            content=self.main_column,
        )

        self.scroll_container = ft.ListView(
            expand=True,
            padding=ft.Padding(16, 28, 16, 36),
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[self.centered_box],
                )
            ],
        )

        self.page.controls = [
            ft.SafeArea(expand=True, content=self.scroll_container),
        ]
        self._apply_responsive_layout()

    def _show_warning(self, message: str) -> None:
        self.warning_text.value = message
        self.warning_banner.visible = True

    def _dismiss_warning(self) -> None:
        self.warning_banner.visible = False
        self.page.update()

    def _notify_worker_event(self) -> None:
        """Schedule draining worker result_queue safely via page.run_thread."""
        try:
            self.page.run_thread(self._drain_worker_events)
        except Exception:
            self._drain_worker_events()

    def _drain_worker_events(self) -> None:
        events = self.indexer.drain_events()
        if not events:
            return

        need_match_refresh = False
        extra_note = ""

        for ev in events:
            if isinstance(ev, StateUpdatedEvent):
                self.docs = ev.docs
                self.ranker = ev.ranker
                self.searches = ev.searches

                if self.active_doc_name and not any(d.name == self.active_doc_name for d in self.docs):
                    self.active_doc_name = self.docs[0].name if self.docs else None
                elif self.active_doc_name is None and self.docs:
                    self.active_doc_name = self.docs[0].name

                if ev.storage_error:
                    self._show_warning(
                        f"Storage warning: {ev.storage_error}. Your changes could not be saved."
                    )
                if ev.errors:
                    self._show_warning(" • ".join(ev.errors))

                if ev.added_count > 0:
                    extra_note = f"Loaded {ev.added_count} file(s)."
                    if self.docs:
                        self.active_doc_name = self.docs[-1].name

                # Refresh suggestion dropdown after any file/trie update
                self._refresh_suggestions(self.current_raw_input)
                self.history_section.update_stats(
                    doc_count=len(self.docs),
                    records=self.searches,
                    extra_note=extra_note,
                    reduce_animations=self.reduce_animations,
                )
                if ev.refresh_query and self.active_query:
                    need_match_refresh = True
                else:
                    self.viewer.update_state(
                        docs=self.docs,
                        active_doc_name=self.active_doc_name,
                        match_result=self.match_result,
                        current_hit_index=self.current_hit_index,
                        match_inside_words=self.match_inside_words,
                        reduce_animations=self.reduce_animations,
                    )

            elif isinstance(ev, MatchCompletedEvent):
                if ev.generation != self._match_generation:
                    continue
                self.match_result = ev.result
                hits = ev.result.hits
                self.current_hit_index = 0 if hits else -1
                if hits:
                    self.active_doc_name = hits[0].doc

                self.viewer.update_state(
                    docs=self.docs,
                    active_doc_name=self.active_doc_name,
                    match_result=self.match_result,
                    current_hit_index=self.current_hit_index,
                    match_inside_words=self.match_inside_words,
                    reduce_animations=self.reduce_animations,
                )
                if hits:
                    self.viewer.scroll_to_hit(hits[0], self._safe_page_update)
                    try:
                        self.scroll_container.scroll_to(key="viewer-anchor", duration=200)
                    except Exception:
                        pass

                self._update_result_card_after_match()

        if need_match_refresh:
            self._start_background_match(self.active_query)

        self._safe_page_update()

    def _safe_page_update(self) -> None:
        try:
            self.page.update()
        except Exception:
            pass

    def _refresh_suggestions(self, raw_text: str) -> None:
        self.current_raw_input = raw_text
        self.active_suggestion_index = -1
        if not raw_text.strip():
            self.current_suggestions = []
            self.suggestions_card.hide()
            self.search_header.set_status("")
            return

        t0 = time.perf_counter()
        suggestions = self.ranker.trie.suggest(raw_text)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.current_suggestions = suggestions
        self.suggestions_card.show_suggestions(
            raw_input=raw_text,
            suggestions=suggestions,
            active_index=self.active_suggestion_index,
        )
        if suggestions:
            self.search_header.set_status(
                f"{len(suggestions)} suggestion(s) in {elapsed_ms:.3f} ms"
            )
        else:
            self.search_header.set_status("")

    def _on_query_change(self, raw_text: str) -> None:
        self._refresh_suggestions(raw_text)
        self.page.update()

    def _on_suggestion_selected(self, word: str) -> None:
        self.do_search(word)

    def _on_suggestion_completed(self, word: str) -> None:
        """Fill input without running a search."""
        self.search_header.set_input_value(word)
        self._refresh_suggestions(word)
        self.page.update()

    def do_search(self, raw_text: str) -> None:
        """Persist search rank (+1 if >=2 chars), highlight matches, and refresh UI."""
        cleaned = clean(raw_text)
        if not cleaned:
            return

        self.search_header.set_input_value("")
        self.current_raw_input = ""
        self.current_suggestions = []
        self.active_suggestion_index = -1
        self.suggestions_card.hide()
        self.search_header.set_status("")

        if not is_valid_history_query(cleaned):
            self.active_query = ""
            self.match_result = None
            self.current_hit_index = -1
            self.viewer.update_state(
                docs=self.docs,
                active_doc_name=self.active_doc_name,
                match_result=None,
                current_hit_index=-1,
                match_inside_words=self.match_inside_words,
                reduce_animations=self.reduce_animations,
            )
            self.search_header.show_result(
                f"Searched: {cleaned}",
                "Queries under 2 characters are ignored for ranking and highlighting.",
            )
            self.page.update()
            return

        now = time.time()
        record, save_res = self.storage.record_search(cleaned, now=now)
        self._last_search_saved = save_res.ok
        if save_res.ok and record is not None:
            self.ranker.apply_personal_record(record, now=now)
            self._last_searched_count = record.count
            updated = [r for r in self.searches if r.word != record.word]
            updated.append(record)
            self.searches = updated
        else:
            self._show_warning(
                save_res.error or f"Could not save '{cleaned}' to local storage."
            )
            existing = next((r for r in self.searches if r.word == cleaned), None)
            self._last_searched_count = existing.count if existing else 0

        self.history_section.update_stats(
            doc_count=len(self.docs),
            records=self.searches,
            reduce_animations=self.reduce_animations,
        )

        self.active_query = cleaned
        if not self.docs:
            self.match_result = None
            self.current_hit_index = -1
            self.viewer.update_state(
                docs=self.docs,
                active_doc_name=self.active_doc_name,
                match_result=None,
                current_hit_index=-1,
                match_inside_words=self.match_inside_words,
                reduce_animations=self.reduce_animations,
            )
            self._update_result_card_after_match()
        else:
            self._start_background_match(cleaned)

        self.page.update()

    def _start_background_match(self, query: str) -> None:
        self._match_generation += 1
        gen = self._match_generation
        self.viewer.set_matching(True)
        docs_snapshot = [(d.name, d.pages) for d in self.docs]
        self.indexer.submit_match(
            docs_snapshot=docs_snapshot,
            query=query,
            match_inside_words=self.match_inside_words,
            generation=gen,
        )

    def _update_result_card_after_match(self) -> None:
        if not self.active_query:
            return
        save_note = "" if self._last_search_saved else " Could not save this search to SQLite."
        rank_note = (
            f"Rank updated (+1). Searched {self._last_searched_count} time(s) so far."
            if self._last_search_saved
            else "Search rank was not saved due to a storage error."
        )
        if not self.docs:
            tail = "Add a file to see where it appears."
        elif self.match_result and self.match_result.hits:
            file_count = len({h.doc for h in self.match_result.hits})
            tail = f"Found in {file_count} file(s). Showing the first match below."
        else:
            tail = "Not found in your files."
        self.search_header.show_result(
            f"Searched: {self.active_query}",
            f"{rank_note}{save_note} {tail}".strip(),
        )

    def clear_highlight(self) -> None:
        """Clear document highlights and remove stale search result summary card."""
        self._match_generation += 1
        self.active_query = ""
        self.match_result = None
        self.current_hit_index = -1
        self.search_header.clear_result()
        self.viewer.update_state(
            docs=self.docs,
            active_doc_name=self.active_doc_name,
            match_result=None,
            current_hit_index=-1,
            match_inside_words=self.match_inside_words,
            reduce_animations=self.reduce_animations,
        )
        self.page.update()

    def _show_hit(self, index: int) -> None:
        if not self.match_result or not self.match_result.hits:
            return
        hits = self.match_result.hits
        self.current_hit_index = index % len(hits)
        hit = hits[self.current_hit_index]
        self.active_doc_name = hit.doc
        self.viewer.update_state(
            docs=self.docs,
            active_doc_name=self.active_doc_name,
            match_result=self.match_result,
            current_hit_index=self.current_hit_index,
            match_inside_words=self.match_inside_words,
            reduce_animations=self.reduce_animations,
        )
        self.viewer.scroll_to_hit(hit, self._safe_page_update)
        self.page.update()

    def _on_select_tab(self, doc_name: str) -> None:
        self.active_doc_name = doc_name
        self.viewer._visible_center_page = 0
        self.viewer.update_state(
            docs=self.docs,
            active_doc_name=self.active_doc_name,
            match_result=self.match_result,
            current_hit_index=self.current_hit_index,
            match_inside_words=self.match_inside_words,
            reduce_animations=self.reduce_animations,
        )
        self.page.update()

    def _on_toggle_learn_mode(self, doc_name: str, next_mode: str) -> None:
        self.indexer.submit_toggle_mode(doc_name, next_mode)

    def _on_toggle_inside_words(self, enabled: bool) -> None:
        self.match_inside_words = enabled
        res = self.storage.set_setting("match_inside_words", "1" if enabled else "0")
        if not res.ok and res.error:
            self._show_warning(res.error)
        if self.active_query and self.docs:
            self._start_background_match(self.active_query)
        else:
            self.viewer.update_state(
                docs=self.docs,
                active_doc_name=self.active_doc_name,
                match_result=self.match_result,
                current_hit_index=self.current_hit_index,
                match_inside_words=self.match_inside_words,
                reduce_animations=self.reduce_animations,
            )
        self.page.update()

    def _on_toggle_reduce_animations(self, enabled: bool) -> None:
        self.reduce_animations = enabled
        self.storage.set_setting("reduce_animations", "1" if enabled else "0")
        self.viewer.update_state(
            docs=self.docs,
            active_doc_name=self.active_doc_name,
            match_result=self.match_result,
            current_hit_index=self.current_hit_index,
            match_inside_words=self.match_inside_words,
            reduce_animations=self.reduce_animations,
        )
        self.page.update()

    def _trigger_file_picker(self) -> None:
        self.file_picker.pick_files(
            dialog_title="Add .txt, .md, or .csv files",
            allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt", "md", "csv"],
            with_data=True,
        )

    def _on_files_picked(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return

        rejected_ext: list[str] = []
        queue_items: list[PendingFileInput] = []
        for f in e.files:
            name = f.name or "document.txt"
            if not name.lower().endswith(ALLOWED_EXTENSIONS):
                rejected_ext.append(name)
                continue
            raw_bytes: bytes | None = getattr(f, "bytes", None)
            queue_items.append(
                PendingFileInput(
                    target_name=name,
                    raw_bytes=raw_bytes,
                    file_path=f.path,
                )
            )

        if rejected_ext:
            self._show_warning(
                f"Unsupported file type: {', '.join(rejected_ext)}. Use .txt, .md, or .csv."
            )
            self.page.update()

        if not queue_items:
            return

        self._pending_raw_files = queue_items
        self._resolved_files = []
        self._resolve_next_file_conflict()

    def _resolve_next_file_conflict(self) -> None:
        existing_names = {d.name for d in self.docs} | {
            item.target_name for item in self._resolved_files
        }
        while self._pending_raw_files:
            item = self._pending_raw_files[0]
            if item.target_name not in existing_names:
                self._pending_raw_files.pop(0)
                self._resolved_files.append(item)
                continue

            alt_name = _unique_copy_name(item.target_name, existing_names)

            def _replace() -> None:
                self._close_active_dialog()
                current = self._pending_raw_files.pop(0)
                self._resolved_files.append(current)
                self._resolve_next_file_conflict()

            def _keep_both() -> None:
                self._close_active_dialog()
                current = self._pending_raw_files.pop(0)
                self._resolved_files.append(
                    PendingFileInput(
                        target_name=alt_name,
                        raw_bytes=current.raw_bytes,
                        file_path=current.file_path,
                    )
                )
                self._resolve_next_file_conflict()

            def _cancel_one() -> None:
                self._close_active_dialog()
                self._pending_raw_files.pop(0)
                self._resolve_next_file_conflict()

            dlg = build_duplicate_file_dialog(
                filename=item.target_name,
                suggested_alt_name=alt_name,
                palette=self.palette,
                on_replace=_replace,
                on_keep_both=_keep_both,
                on_cancel=_cancel_one,
            )
            self._open_dialog(dlg)
            return

        if self._resolved_files:
            self.viewer.set_loading_files(True)
            self.page.update()
            self.indexer.submit_ingest_files(list(self._resolved_files))
            self._resolved_files = []

    def _confirm_remove_doc(self, doc_name: str) -> None:
        def _confirm() -> None:
            self._close_active_dialog()
            self.indexer.submit_remove_doc(doc_name)

        dlg = build_confirm_dialog(
            title="Remove file?",
            message=f'Remove "{doc_name}" from Fulgur Search?',
            confirm_label="Remove",
            palette=self.palette,
            on_confirm=_confirm,
            on_cancel=self._close_active_dialog,
            destructive=True,
        )
        self._open_dialog(dlg)

    def _delete_search_entry(self, word: str) -> None:
        res = self.storage.delete_search(word)
        if not res.ok:
            self._show_warning(res.error or f"Could not delete '{word}'.")
            self.page.update()
            return
        self.searches = [r for r in self.searches if r.word != word]
        self.ranker = Ranker.rebuild(
            [d.terms for d in self.docs],
            self.searches,
            now=time.time(),
            k=TOP_K,
        )
        self._refresh_suggestions(self.current_raw_input)
        self.history_section.update_stats(
            doc_count=len(self.docs),
            records=self.searches,
            reduce_animations=self.reduce_animations,
        )
        self.page.update()

    def _confirm_reset(self) -> None:
        def _confirm() -> None:
            self._close_active_dialog()
            self._start_undoable_reset()

        dlg = build_confirm_dialog(
            title="Reset learned data?",
            message="Forget your searches and loaded files? You will have 8 seconds to undo.",
            confirm_label="Reset",
            palette=self.palette,
            on_confirm=_confirm,
            on_cancel=self._close_active_dialog,
            destructive=True,
        )
        self._open_dialog(dlg)

    def _start_undoable_reset(self) -> None:
        if self._reset_purge_timer is not None:
            self._reset_purge_timer.cancel()
            self._reset_purge_timer = None

        snapshot, snap_res = self.storage.create_snapshot()
        if not snap_res.ok:
            self._show_warning(snap_res.error or "Could not snapshot data before reset.")
            self.page.update()
            return
        self._pending_reset_snapshot = snapshot

        # Clear visible state immediately; defer permanent purge until ~8s snackbar expires
        self.docs = []
        self.searches = []
        self.ranker = Ranker(k=TOP_K)
        self.active_doc_name = None
        self.active_query = ""
        self.match_result = None
        self.current_hit_index = -1
        self.search_header.clear_result()
        self._refresh_suggestions(self.current_raw_input)
        self.viewer.update_state(
            docs=[],
            active_doc_name=None,
            match_result=None,
            current_hit_index=-1,
            match_inside_words=self.match_inside_words,
            reduce_animations=self.reduce_animations,
        )
        self.history_section.update_stats(
            doc_count=0,
            records=[],
            reduce_animations=self.reduce_animations,
        )

        self._reset_purge_timer = threading.Timer(
            RESET_UNDO_SECONDS,
            self._finalize_reset_purge,
        )
        self._reset_purge_timer.daemon = True
        self._reset_purge_timer.start()

        snack = ft.SnackBar(
            content=ft.Text("Learned data reset."),
            action="Undo",
            duration=int(RESET_UNDO_SECONDS * 1000),
            on_action=lambda _: self._undo_reset(),
        )
        self.page.open(snack)
        self.page.update()

    def _undo_reset(self) -> None:
        if self._reset_purge_timer is not None:
            self._reset_purge_timer.cancel()
            self._reset_purge_timer = None
        snapshot = self._pending_reset_snapshot
        self._pending_reset_snapshot = None
        if snapshot is None:
            return
        res = self.storage.restore_snapshot(snapshot)
        if not res.ok:
            self._show_warning(res.error or "Could not restore data.")
            self.page.update()
            return
        self.indexer.submit_rebuild_from_storage()

    def _finalize_reset_purge(self) -> None:
        self._reset_purge_timer = None
        if self._pending_reset_snapshot is None:
            return
        self._pending_reset_snapshot = None
        res = self.storage.purge_all()
        if not res.ok:
            self._show_warning(res.error or "Failed to purge reset data.")
            self._safe_page_update()
        else:
            self.indexer.submit_rebuild_from_storage()

    def _open_dialog(self, dlg: ft.AlertDialog) -> None:
        self._active_dialog = dlg
        self.page.open(dlg)
        self.page.update()

    def _close_active_dialog(self) -> None:
        if self._active_dialog is not None:
            try:
                self.page.close(self._active_dialog)
            except Exception:
                pass
            self._active_dialog = None
            self.page.update()

    def _on_keyboard_event(self, e: ft.KeyboardEvent) -> None:
        key = e.key
        if key in ("Go Back", "Browser Back", "Back"):
            if self._handle_back_action():
                return

        if self._active_dialog is not None:
            if key == "Escape":
                self._close_active_dialog()
            return

        if key == "ArrowDown" and self.current_suggestions:
            self.active_suggestion_index = (self.active_suggestion_index + 1) % len(
                self.current_suggestions
            )
            self.suggestions_card.show_suggestions(
                self.current_raw_input,
                self.current_suggestions,
                self.active_suggestion_index,
            )
            self.page.update()
        elif key == "ArrowUp" and self.current_suggestions:
            total = len(self.current_suggestions)
            if self.active_suggestion_index <= 0:
                self.active_suggestion_index = total - 1
            else:
                self.active_suggestion_index -= 1
            self.suggestions_card.show_suggestions(
                self.current_raw_input,
                self.current_suggestions,
                self.active_suggestion_index,
            )
            self.page.update()
        elif key == "Tab" and self.current_suggestions:
            pick = (
                self.active_suggestion_index
                if self.active_suggestion_index >= 0
                else 0
            )
            completed = self.current_suggestions[pick]
            self._on_suggestion_completed(completed)
        elif key == "Enter":
            if 0 <= self.active_suggestion_index < len(self.current_suggestions):
                self.do_search(self.current_suggestions[self.active_suggestion_index])
            else:
                self.do_search(self.search_header.query_input.value or "")
        elif key == "Escape":
            if self.suggestions_card.visible or self.current_raw_input:
                self.search_header.set_input_value("")
                self._refresh_suggestions("")
                self.page.update()

    def _handle_back_action(self) -> bool:
        """Close dropdown first, then dialogs, then allow exiting."""
        if self.suggestions_card.visible:
            self.suggestions_card.hide()
            self.search_header.set_status("")
            self.active_suggestion_index = -1
            self.page.update()
            return True
        if self._active_dialog is not None:
            self._close_active_dialog()
            return True
        return False

    def _on_view_pop(self, _e: ft.ViewPopEvent) -> None:
        if not self._handle_back_action():
            try:
                self.page.window.close()
            except Exception:
                pass

    def _on_brightness_change(self, _e: ft.ControlEvent) -> None:
        self.palette = self._resolve_palette()
        self.page.bgcolor = self.palette.bg
        compact = (self.page.width or 400) < 420
        self.search_header.apply_palette(self.palette, compact=compact)
        self.suggestions_card.apply_palette(self.palette)
        self.viewer.apply_palette(self.palette)
        self.history_section.apply_palette(self.palette)
        self._refresh_suggestions(self.current_raw_input)
        self.history_section.update_stats(
            doc_count=len(self.docs),
            records=self.searches,
            reduce_animations=self.reduce_animations,
        )
        self.page.update()

    def _on_resize(self, _e: ft.ControlEvent) -> None:
        self._apply_responsive_layout()
        self.page.update()

    def _apply_responsive_layout(self) -> None:
        width = self.page.width or 400
        compact = width < 420
        h_pad = 12 if compact else 16
        v_pad = 18 if compact else 36
        self.centered_box.width = min(MAX_CONTENT_WIDTH, max(296, width - 2 * h_pad))
        self.scroll_container.padding = ft.Padding(h_pad, v_pad, h_pad, 32)
        self.search_header.apply_palette(self.palette, compact=compact)

    def _on_page_close(self, _e: ft.ControlEvent) -> None:
        if self._pending_reset_snapshot is not None:
            if self._reset_purge_timer is not None:
                self._reset_purge_timer.cancel()
            self._finalize_reset_purge()
        self.indexer.stop()
