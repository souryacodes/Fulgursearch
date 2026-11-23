"""Lazy paginated document viewer, tabs, match hit bar, hit list, and page footer."""

from __future__ import annotations

import threading
from typing import Callable

import flet as ft

from config import MAX_HITS, PULSE_DURATION_MS, VIEWER_RENDER_WINDOW
from engine.file_learner import format_mode_label
from engine.matcher import LineSpan, MatchHit, MatchResult
from engine.paginator import Page
from theme import (
    GUTTER_WIDTH,
    HITS_MAX_HEIGHT,
    MIN_TOUCH_TARGET,
    PAGE_CARD_MAX_WIDTH,
    RADIUS_BADGE,
    RADIUS_BUTTON,
    RADIUS_CARD,
    RADIUS_MARK,
    RADIUS_PAGE,
    RADIUS_TAB,
    VIEWER_HEIGHT,
    VIEWER_PAD,
    ThemePalette,
)
from workers.indexer import DocumentState


def _estimate_page_height(page: Page) -> float:
    """Estimate rendered pixel height of a page card for smooth lazy scroll windows."""
    return 56.0 + max(1, len(page.lines)) * 24.0


class DocumentViewer(ft.Container):
    """Tabbed paginated document viewer with lazy page windowing and match navigation."""

    def __init__(
        self,
        palette: ThemePalette,
        on_add_files: Callable[[], None],
        on_select_tab: Callable[[str], None],
        on_request_remove_doc: Callable[[str], None],
        on_toggle_learn_mode: Callable[[str, str], None],
        on_toggle_inside_words: Callable[[bool], None],
        on_prev_hit: Callable[[], None],
        on_next_hit: Callable[[], None],
        on_clear_highlight: Callable[[], None],
        on_select_hit: Callable[[int], None],
    ) -> None:
        self.palette = palette
        self._on_add_files = on_add_files
        self._on_select_tab = on_select_tab
        self._on_request_remove_doc = on_request_remove_doc
        self._on_toggle_learn_mode = on_toggle_learn_mode
        self._on_toggle_inside_words = on_toggle_inside_words
        self._on_prev_hit = on_prev_hit
        self._on_next_hit = on_next_hit
        self._on_clear_highlight = on_clear_highlight
        self._on_select_hit = on_select_hit

        self.docs: list[DocumentState] = []
        self.active_doc_name: str | None = None
        self.match_result: MatchResult | None = None
        self.current_hit_index: int = -1
        self.match_inside_words: bool = False
        self.reduce_animations: bool = False
        self.is_loading_files: bool = False
        self.is_matching: bool = False

        self._visible_center_page: int = 0  # 0-based page index
        self._page_heights: list[float] = []
        self._page_offsets: list[float] = []
        self._pulse_active: bool = False
        self._pulse_timer: threading.Timer | None = None

        # Header: scrollable tabs + Add files button
        self.tabs_row = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self.add_files_btn = ft.Semantics(
            label="Add files",
            button=True,
            content=ft.FilledTonalButton(
                content=ft.Text("Add files", size=14, color=palette.text, weight=ft.FontWeight.W_500),
                style=ft.ButtonStyle(
                    bgcolor={
                        ft.ControlState.DEFAULT: palette.light_btn,
                        ft.ControlState.PRESSED: palette.light_btn_pressed,
                    },
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                ),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: self._on_add_files(),
            ),
        )
        self.header_box = ft.Container(
            padding=ft.Padding(12, 10, 12, 10),
            border=ft.Border(bottom=ft.BorderSide(1, palette.divider_main)),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.tabs_row, self.add_files_btn],
            ),
        )

        # Learned-as bar per active document
        self.learn_label = ft.Text("", size=13, color=palette.muted)
        self.learn_toggle_btn = ft.TextButton(
            content=ft.Text("", size=13, color=palette.primary),
            height=MIN_TOUCH_TARGET,
            on_click=self._handle_toggle_mode_click,
        )
        self.learn_bar = ft.Container(
            visible=False,
            padding=ft.Padding(12, 2, 12, 2),
            border=ft.Border(bottom=ft.BorderSide(1, palette.divider_main)),
            content=ft.Row(
                spacing=8,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[self.learn_label, self.learn_toggle_btn],
            ),
        )

        # Hit bar + Match inside words toggle
        self.hit_info_text = ft.Text("", size=14, color=palette.text, expand=True)
        self.inside_words_switch = ft.Switch(
            value=False,
            label="Match inside words",
            label_position=ft.LabelPosition.LEFT,
            active_color=palette.primary,
            on_change=lambda e: self._on_toggle_inside_words(bool(e.control.value)),
        )
        self.prev_btn = self._light_action_btn("Previous", self._on_prev_hit)
        self.next_btn = self._light_action_btn("Next", self._on_next_hit)
        self.clear_btn = self._light_action_btn("Clear highlight", self._on_clear_highlight)
        self.hit_bar = ft.Container(
            visible=False,
            bgcolor=palette.hit_bar_bg,
            border=ft.Border(bottom=ft.BorderSide(1, palette.hit_bar_border)),
            padding=ft.Padding(12, 8, 12, 8),
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Semantics(live_region=True, content=self.hit_info_text),
                            ft.Semantics(
                                label="Match inside words toggle",
                                content=self.inside_words_switch,
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        wrap=True,
                        controls=[self.prev_btn, self.next_btn, self.clear_btn],
                    ),
                ],
            ),
        )

        # Hit list (max height 150)
        self.hits_list = ft.ListView(
            spacing=0,
            height=HITS_MAX_HEIGHT,
            visible=False,
        )
        self.hits_divider = ft.Divider(height=1, thickness=1, color=palette.divider_main, visible=False)

        # Lazy viewer ListView
        self.pages_list = ft.ListView(
            spacing=14,
            padding=VIEWER_PAD,
            expand=True,
            on_scroll=self._handle_viewer_scroll,
        )
        self.viewer_box = ft.Container(
            height=VIEWER_HEIGHT,
            bgcolor=palette.viewer_bg,
            content=self.pages_list,
        )

        # Footer: Page [n] of N [Go]
        self.pg_input = ft.TextField(
            value="1",
            width=72,
            text_size=16,  # >= 16sp mobile input guideline
            keyboard_type=ft.KeyboardType.NUMBER,
            content_padding=ft.Padding(10, 8, 10, 8),
            border_radius=RADIUS_TAB,
            border_color=palette.border,
            focused_border_color=palette.primary,
            bgcolor=palette.card_bg,
            text_style=ft.TextStyle(color=palette.text, size=16),
            on_submit=lambda _: self._go_to_input_page(),
        )
        self.pg_total_text = ft.Text("of 0", size=14, color=palette.muted)
        self.pg_go_btn = self._light_action_btn("Go", self._go_to_input_page)
        self.footer_box = ft.Container(
            padding=ft.Padding(12, 8, 12, 8),
            border=ft.Border(top=ft.BorderSide(1, palette.divider_main)),
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Page", size=14, color=palette.muted),
                    ft.Semantics(label="Page number input", text_field=True, content=self.pg_input),
                    self.pg_total_text,
                    self.pg_go_btn,
                ],
            ),
        )

        super().__init__(
            bgcolor=palette.card_bg,
            border_radius=RADIUS_CARD,
            margin=ft.Margin(0, 18, 0, 0),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(
                blur_radius=10,
                spread_radius=0,
                color="#0F000000",
                offset=ft.Offset(0, 2),
            ),
            content=ft.Column(
                spacing=0,
                controls=[
                    self.header_box,
                    self.learn_bar,
                    self.hit_bar,
                    self.hits_list,
                    self.hits_divider,
                    self.viewer_box,
                    self.footer_box,
                ],
            ),
        )
        self.render_all()

    def _light_action_btn(self, label: str, on_click: Callable[[], None]) -> ft.FilledTonalButton:
        return ft.FilledTonalButton(
            content=ft.Text(label, size=14, color=self.palette.text),
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT: self.palette.light_btn,
                    ft.ControlState.PRESSED: self.palette.light_btn_pressed,
                },
                shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                padding=ft.Padding(14, 0, 14, 0),
            ),
            height=MIN_TOUCH_TARGET,
            on_click=lambda _: on_click(),
        )

    def _active_doc(self) -> DocumentState | None:
        if not self.active_doc_name:
            return None
        for doc in self.docs:
            if doc.name == self.active_doc_name:
                return doc
        return None

    def _handle_toggle_mode_click(self, _e: ft.ControlEvent) -> None:
        doc = self._active_doc()
        if doc is None:
            return
        next_mode = "prose" if doc.effective_mode == "wordlist" else "wordlist"
        self._on_toggle_learn_mode(doc.name, next_mode)

    def set_loading_files(self, loading: bool) -> None:
        self.is_loading_files = loading
        self.render_pages()

    def set_matching(self, matching: bool) -> None:
        self.is_matching = matching
        if matching:
            self.render_hits_skeleton()

    def update_state(
        self,
        docs: list[DocumentState],
        active_doc_name: str | None,
        match_result: MatchResult | None,
        current_hit_index: int,
        match_inside_words: bool,
        reduce_animations: bool,
    ) -> None:
        self.docs = docs
        self.active_doc_name = active_doc_name
        self.match_result = match_result
        self.current_hit_index = current_hit_index
        self.match_inside_words = match_inside_words
        self.reduce_animations = reduce_animations
        self.inside_words_switch.value = match_inside_words
        self.is_loading_files = False
        self.is_matching = False
        self.render_all()

    def render_all(self) -> None:
        self.render_tabs()
        self.render_learn_bar()
        self.render_hits()
        self.render_pages()

    def render_tabs(self) -> None:
        if not self.docs:
            self.tabs_row.controls = [
                ft.Text("No files yet", size=13, color=self.palette.muted),
            ]
            return

        counts = self.match_result.file_counts if self.match_result else {}
        has_query = bool(self.match_result and self.match_result.query)
        tabs: list[ft.Control] = []

        for doc in self.docs:
            is_selected = doc.name == self.active_doc_name
            bg = self.palette.primary if is_selected else self.palette.light_btn
            fg = self.palette.on_primary if is_selected else self.palette.text

            label_parts: list[ft.Control] = [
                ft.Text(doc.name, size=13, color=fg, weight=ft.FontWeight.W_600 if is_selected else ft.FontWeight.NORMAL)
            ]
            count = counts.get(doc.name, 0)
            if has_query and count > 0:
                badge_text = f"{MAX_HITS}+" if count > MAX_HITS else str(count)
                label_parts.append(
                    ft.Container(
                        bgcolor=self.palette.badge_bg,
                        border_radius=RADIUS_BADGE,
                        padding=ft.Padding(6, 1, 6, 1),
                        content=ft.Text(
                            badge_text,
                            size=11,
                            color=self.palette.badge_text,
                            weight=ft.FontWeight.BOLD,
                        ),
                    )
                )

            select_btn = ft.TextButton(
                content=ft.Row(spacing=6, tight=True, controls=label_parts),
                height=MIN_TOUCH_TARGET,
                style=ft.ButtonStyle(
                    padding=ft.Padding(12, 0, 8, 0),
                    shape=ft.RoundedRectangleBorder(radius=0),
                ),
                on_click=lambda _e, name=doc.name: self._on_select_tab(name),
            )

            remove_btn = ft.Semantics(
                label=f"Remove {doc.name}",
                button=True,
                content=ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=16,
                    icon_color=fg,
                    width=MIN_TOUCH_TARGET,
                    height=MIN_TOUCH_TARGET,
                    tooltip=f"Remove {doc.name}",
                    on_click=lambda _e, name=doc.name: self._on_request_remove_doc(name),
                ),
            )

            tab = ft.Semantics(
                label=f"File tab {doc.name}" + (f", {count} matches" if has_query and count else ""),
                selected=is_selected,
                content=ft.Container(
                    bgcolor=bg,
                    border_radius=RADIUS_TAB,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    content=ft.Row(spacing=0, tight=True, controls=[select_btn, remove_btn]),
                ),
            )
            tabs.append(tab)

        self.tabs_row.controls = tabs

    def render_learn_bar(self) -> None:
        doc = self._active_doc()
        if doc is None:
            self.learn_bar.visible = False
            return
        mode_text = format_mode_label(doc.effective_mode)
        other_text = "prose" if doc.effective_mode == "wordlist" else "word list"
        self.learn_label.value = f"Learned as: {mode_text}"
        self.learn_toggle_btn.content = ft.Text(
            f"Switch to {other_text}",
            size=13,
            color=self.palette.primary,
            weight=ft.FontWeight.W_600,
        )
        self.learn_bar.visible = True

    def render_hits_skeleton(self) -> None:
        self.hit_bar.visible = True
        self.hit_info_text.value = "Searching files..."
        self.hits_list.controls = [
            ft.Container(
                padding=ft.Padding(14, 10, 14, 10),
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Container(width=140, height=11, bgcolor=self.palette.skeleton_bg, border_radius=4),
                        ft.Container(width=240, height=14, bgcolor=self.palette.skeleton_bg, border_radius=4),
                    ],
                ),
            )
            for _ in range(3)
        ]
        self.hits_list.visible = True
        self.hits_divider.visible = True

    def render_hits(self) -> None:
        mr = self.match_result
        if mr is None or not mr.query:
            self.hit_bar.visible = False
            self.hits_list.visible = False
            self.hits_divider.visible = False
            self.hits_list.controls = []
            return

        self.hit_bar.visible = True
        hits = mr.hits
        self.prev_btn.disabled = len(hits) < 2
        self.next_btn.disabled = len(hits) < 2

        if not hits:
            self.hit_info_text.value = f'No match for "{mr.query}" in your files.'
            self.hits_list.visible = False
            self.hits_divider.visible = False
            self.hits_list.controls = []
            return

        cur_hit = hits[self.current_hit_index] if 0 <= self.current_hit_index < len(hits) else hits[0]
        if mr.is_capped:
            self.hit_info_text.value = (
                f'{MAX_HITS}+ matches (showing first {MAX_HITS}) — '
                f'match {self.current_hit_index + 1} of {len(hits)} '
                f'({cur_hit.doc}, page {cur_hit.page}, line {cur_hit.line})'
            )
        else:
            self.hit_info_text.value = (
                f'"{mr.query}": match {self.current_hit_index + 1} of {len(hits)} '
                f'({cur_hit.doc}, page {cur_hit.page}, line {cur_hit.line})'
            )

        rows: list[ft.Control] = []
        for idx, hit in enumerate(hits):
            is_sel = idx == self.current_hit_index
            rows.append(self._build_hit_row(idx, hit, is_sel))

        self.hits_list.controls = rows
        self.hits_list.visible = True
        self.hits_divider.visible = True

    def _build_hit_row(self, idx: int, hit: MatchHit, is_selected: bool) -> ft.Control:
        from_i = max(0, hit.idx - 40)
        to_i = min(len(hit.text), hit.idx + hit.len + 60)
        prefix = ("…" if from_i > 0 else "") + hit.text[from_i : hit.idx]
        matched = hit.text[hit.idx : hit.idx + hit.len]
        suffix = hit.text[hit.idx + hit.len : to_i] + ("…" if to_i < len(hit.text) else "")

        snippet = ft.Text(
            spans=[
                ft.TextSpan(prefix, style=ft.TextStyle(color=self.palette.text, size=14)),
                ft.TextSpan(
                    matched,
                    style=ft.TextStyle(
                        color=self.palette.highlight_text,
                        bgcolor=self.palette.highlight_bg,
                        size=14,
                        weight=ft.FontWeight.W_600,
                    ),
                ),
                ft.TextSpan(suffix, style=ft.TextStyle(color=self.palette.text, size=14)),
            ],
            max_lines=2,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        return ft.Semantics(
            label=f"Match {idx + 1}: {hit.doc}, page {hit.page}, line {hit.line}",
            button=True,
            selected=is_selected,
            content=ft.Container(
                key=f"hit-{idx}",
                bgcolor=self.palette.hit_selected if is_selected else self.palette.card_bg,
                padding=ft.Padding(14, 8, 14, 8),
                border=ft.Border(bottom=ft.BorderSide(1, self.palette.divider_soft)),
                on_click=lambda _e, hit_idx=idx: self._on_select_hit(hit_idx),
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(
                            f"{hit.doc}, page {hit.page}, line {hit.line}",
                            size=12,
                            color=self.palette.muted,
                        ),
                        snippet,
                    ],
                ),
            ),
        )

    def render_pages(self) -> None:
        if self.is_loading_files:
            self.pages_list.controls = [self._build_page_skeleton(560) for _ in range(2)]
            self.pg_total_text.value = "of …"
            return

        doc = self._active_doc()
        if doc is None:
            self.pages_list.controls = [
                ft.Container(
                    padding=ft.Padding(24, 70, 24, 70),
                    alignment=ft.alignment.center,
                    content=ft.Text(
                        "No files yet. Tap Add files and choose a .txt, .md, or .csv file. "
                        "Its text appears here page by page, and its words become suggestions.",
                        size=15,
                        color=self.palette.muted,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            ]
            self.pg_total_text.value = "of 0"
            self.pg_input.value = "1"
            self._page_heights = []
            self._page_offsets = []
            return

        pages = doc.pages
        total_pages = len(pages)
        self.pg_total_text.value = f"of {total_pages}"

        self._page_heights = [_estimate_page_height(pg) for pg in pages]
        self._page_offsets = []
        acc = 0.0
        for h in self._page_heights:
            self._page_offsets.append(acc)
            acc += h + 14.0

        self._visible_center_page = max(0, min(self._visible_center_page, total_pages - 1))
        lo = max(0, self._visible_center_page - VIEWER_RENDER_WINDOW)
        hi = min(total_pages - 1, self._visible_center_page + VIEWER_RENDER_WINDOW)

        cur_hit: MatchHit | None = None
        if self.match_result and 0 <= self.current_hit_index < len(self.match_result.hits):
            candidate = self.match_result.hits[self.current_hit_index]
            if candidate.doc == doc.name:
                cur_hit = candidate

        controls: list[ft.Control] = []
        for idx, page in enumerate(pages):
            if lo <= idx <= hi:
                controls.append(self._build_page_card(doc.name, page, total_pages, cur_hit))
            else:
                controls.append(self._build_page_skeleton(self._page_heights[idx], page_key=f"page-{page.number}"))

        self.pages_list.controls = controls
        self.pg_input.value = str(self._visible_center_page + 1)

    def _build_page_skeleton(self, height: float, page_key: str | None = None) -> ft.Control:
        return ft.Container(
            key=page_key,
            alignment=ft.alignment.center,
            content=ft.Container(
                width=PAGE_CARD_MAX_WIDTH,
                height=height,
                bgcolor=self.palette.card_bg,
                border_radius=RADIUS_PAGE,
                padding=ft.Padding(18, 14, 18, 18),
                content=ft.Column(
                    spacing=10,
                    controls=[
                        ft.Container(width=120, height=12, bgcolor=self.palette.skeleton_bg, border_radius=3),
                        ft.Container(height=12, bgcolor=self.palette.skeleton_bg, border_radius=3),
                        ft.Container(width=300, height=12, bgcolor=self.palette.skeleton_bg, border_radius=3),
                    ],
                ),
            ),
        )

    def _build_page_card(
        self,
        doc_name: str,
        page: Page,
        total_pages: int,
        cur_hit: MatchHit | None,
    ) -> ft.Control:
        cur_k = cur_hit.k if cur_hit is not None else -1
        line_spans_map = self.match_result.line_spans if self.match_result else {}

        page_header = ft.Container(
            padding=ft.Padding(0, 0, 0, 6),
            margin=ft.Margin(0, 0, 0, 10),
            border=ft.Border(bottom=ft.BorderSide(1, self.palette.divider_main)),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(f"Page {page.number} of {total_pages}", size=12, color=self.palette.muted),
                    ft.Text(doc_name, size=12, color=self.palette.muted, overflow=ft.TextOverflow.ELLIPSIS),
                ],
            ),
        )

        line_controls: list[ft.Control] = [page_header]
        for line in page.lines:
            spans = line_spans_map.get((doc_name, page.number, line.number), [])
            line_controls.append(self._build_line_row(line.number, line.text, spans, cur_k))

        return ft.Container(
            key=f"page-{page.number}",
            alignment=ft.alignment.center,
            content=ft.Container(
                width=PAGE_CARD_MAX_WIDTH,
                bgcolor=self.palette.card_bg,
                border_radius=RADIUS_PAGE,
                padding=ft.Padding(18, 14, 18, 18),
                shadow=ft.BoxShadow(
                    blur_radius=6,
                    spread_radius=0,
                    color="#24000000",
                    offset=ft.Offset(0, 1),
                ),
                content=ft.Column(spacing=2, controls=line_controls),
            ),
        )

    def _build_line_row(
        self,
        line_no: int,
        text: str,
        spans: list[LineSpan],
        cur_k: int,
    ) -> ft.Control:
        gutter = ft.Container(
            width=GUTTER_WIDTH,
            alignment=ft.alignment.top_right,
            padding=ft.Padding(0, 2, 0, 0),
            content=ft.Text(
                str(line_no),
                size=12,
                color=self.palette.line_no,
                selectable=False,
            ),
        )

        if not spans:
            content_text = ft.Text(
                text if text else " ",
                size=15,
                color=self.palette.text,
                selectable=True,
                expand=True,
            )
        else:
            sorted_spans = sorted(spans, key=lambda s: (s.start, s.end))
            text_spans: list[ft.TextSpan] = []
            cursor = 0
            for sp in sorted_spans:
                start = max(cursor, sp.start)
                end = max(start, sp.end)
                if start > cursor:
                    text_spans.append(
                        ft.TextSpan(
                            text[cursor:start],
                            style=ft.TextStyle(size=15, color=self.palette.text),
                        )
                    )
                if end > start:
                    is_current = sp.k == cur_k
                    bg = self.palette.current_match_bg if is_current else self.palette.highlight_bg
                    deco_color = (
                        self.palette.current_match_outline
                        if (is_current and self._pulse_active and not self.reduce_animations)
                        else self.palette.current_match_outline
                    )
                    text_spans.append(
                        ft.TextSpan(
                            text[start:end],
                            style=ft.TextStyle(
                                size=15,
                                color=self.palette.highlight_text,
                                bgcolor=bg,
                                weight=ft.FontWeight.BOLD if is_current else ft.FontWeight.NORMAL,
                                decoration=ft.TextDecoration.UNDERLINE if is_current else None,
                                decoration_color=deco_color if is_current else None,
                                decoration_thickness=2 if is_current else None,
                            ),
                        )
                    )
                    cursor = end
            if cursor < len(text):
                text_spans.append(
                    ft.TextSpan(
                        text[cursor:],
                        style=ft.TextStyle(size=15, color=self.palette.text),
                    )
                )
            content_text = ft.Text(spans=text_spans, size=15, selectable=True, expand=True)

        has_current = any(sp.k == cur_k for sp in spans)
        row = ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[gutter, content_text],
        )
        if has_current:
            border_width = 2 if (self._pulse_active and not self.reduce_animations) else 1
            return ft.Container(
                key=f"cur-hit-{cur_k}",
                border_radius=RADIUS_MARK,
                border=ft.Border.all(border_width, self.palette.current_match_outline),
                animate=None if self.reduce_animations else ft.Animation(300, ft.AnimationCurve.EASE_OUT),
                padding=ft.Padding(2, 1, 2, 1),
                content=row,
            )
        return row

    def scroll_to_hit(self, hit: MatchHit, page_update_cb: Callable[[], None]) -> None:
        """Scroll viewer so the matched page/line sits near ~1/3 viewer height and pulse briefly."""
        doc = self._active_doc()
        if doc is None or not doc.pages:
            return
        target_page_idx = max(0, min(len(doc.pages) - 1, hit.page - 1))
        self._visible_center_page = target_page_idx
        self._trigger_pulse(page_update_cb)
        self.render_pages()

        # Estimate line offset inside the page and position ~1/3 from top of 440dp viewer
        page_obj = doc.pages[target_page_idx]
        line_pos = 0
        for idx, line in enumerate(page_obj.lines):
            if line.number == hit.line:
                line_pos = idx
                break
        base_offset = self._page_offsets[target_page_idx] if target_page_idx < len(self._page_offsets) else 0.0
        target_offset = max(0.0, base_offset + 44.0 + line_pos * 24.0 - (VIEWER_HEIGHT / 3.0))
        duration = 0 if self.reduce_animations else 240
        try:
            self.pages_list.scroll_to(offset=target_offset, duration=duration)
        except Exception:
            pass
        if 0 <= self.current_hit_index < len(self.hits_list.controls):
            try:
                self.hits_list.scroll_to(key=f"hit-{self.current_hit_index}", duration=duration)
            except Exception:
                pass

    def _trigger_pulse(self, page_update_cb: Callable[[], None]) -> None:
        if self._pulse_timer is not None:
            self._pulse_timer.cancel()
            self._pulse_timer = None
        if self.reduce_animations:
            self._pulse_active = False
            return
        self._pulse_active = True

        def _end_pulse() -> None:
            self._pulse_active = False
            self.render_pages()
            page_update_cb()

        self._pulse_timer = threading.Timer(PULSE_DURATION_MS / 1000.0, _end_pulse)
        self._pulse_timer.daemon = True
        self._pulse_timer.start()

    def _handle_viewer_scroll(self, e: ft.OnScrollEvent) -> None:
        if not self._page_offsets:
            return
        top = (e.pixels or 0.0) + 30.0
        new_center = 0
        for idx, off in enumerate(self._page_offsets):
            if off <= top:
                new_center = idx
            else:
                break
        if new_center != self._visible_center_page:
            self._visible_center_page = new_center
            self.pg_input.value = str(new_center + 1)
            self.render_pages()
            if self.page is not None:
                self.page.update()
        else:
            expected = str(new_center + 1)
            if self.pg_input.value != expected:
                self.pg_input.value = expected
                if self.page is not None:
                    self.pg_input.update()

    def _go_to_input_page(self) -> None:
        doc = self._active_doc()
        if doc is None or not doc.pages:
            return
        try:
            num = int((self.pg_input.value or "1").strip())
        except ValueError:
            num = 1
        num = max(1, min(len(doc.pages), num))
        self.pg_input.value = str(num)
        self._visible_center_page = num - 1
        self.render_pages()
        offset = self._page_offsets[num - 1] if (num - 1) < len(self._page_offsets) else 0.0
        duration = 0 if self.reduce_animations else 200
        try:
            self.pages_list.scroll_to(offset=max(0.0, offset - 8.0), duration=duration)
        except Exception:
            pass
        if self.page is not None:
            self.page.update()

    def apply_palette(self, palette: ThemePalette) -> None:
        self.palette = palette
        self.bgcolor = palette.card_bg
        self.header_box.border = ft.Border(bottom=ft.BorderSide(1, palette.divider_main))
        self.learn_bar.border = ft.Border(bottom=ft.BorderSide(1, palette.divider_main))
        self.learn_label.color = palette.muted
        self.hit_bar.bgcolor = palette.hit_bar_bg
        self.hit_bar.border = ft.Border(bottom=ft.BorderSide(1, palette.hit_bar_border))
        self.hit_info_text.color = palette.text
        self.viewer_box.bgcolor = palette.viewer_bg
        self.footer_box.border = ft.Border(top=ft.BorderSide(1, palette.divider_main))
        self.pg_total_text.color = palette.muted
        self.pg_input.bgcolor = palette.card_bg
        self.pg_input.border_color = palette.border
        self.pg_input.focused_border_color = palette.primary
        self.pg_input.text_style = ft.TextStyle(color=palette.text, size=16)
        self.render_all()
