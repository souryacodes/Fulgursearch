"""Ranked suggestion dropdown with bold prefix highlighting, complete action, and skeletons."""

from __future__ import annotations

from typing import Callable

import flet as ft

from engine.trie import bold_prefix_len
from theme import (
    MIN_TOUCH_TARGET,
    RADIUS_CARD,
    SUGGESTION_GAP,
    SUGGESTION_PAD_H,
    SUGGESTION_PAD_V,
    SUGGESTION_RANK_SIZE,
    SUGGESTION_RANK_WIDTH,
    SUGGESTION_TEXT_SIZE,
    ThemePalette,
)


class SuggestionsCard(ft.Container):
    """Autocomplete dropdown card below the search bar."""

    def __init__(
        self,
        palette: ThemePalette,
        on_select: Callable[[str], None],
        on_complete: Callable[[str], None],
    ) -> None:
        self.palette = palette
        self._on_select = on_select
        self._on_complete = on_complete
        self._column = ft.Column(spacing=0, tight=True)
        super().__init__(
            visible=False,
            bgcolor=palette.card_bg,
            border_radius=RADIUS_CARD,
            margin=ft.Margin(0, 8, 0, 0),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(
                blur_radius=10,
                spread_radius=0,
                color="#14000000",
                offset=ft.Offset(0, 2),
            ),
            content=self._column,
        )

    def show_loading(self) -> None:
        """Render skeleton placeholder rows while background indexing completes."""
        rows: list[ft.Control] = []
        for idx in range(3):
            rows.append(
                ft.Container(
                    padding=ft.Padding(SUGGESTION_PAD_H, SUGGESTION_PAD_V, SUGGESTION_PAD_H, SUGGESTION_PAD_V),
                    border=ft.Border(bottom=ft.BorderSide(1, self.palette.divider_main)) if idx < 2 else None,
                    content=ft.Row(
                        spacing=SUGGESTION_GAP,
                        controls=[
                            ft.Container(
                                width=SUGGESTION_RANK_WIDTH,
                                height=14,
                                bgcolor=self.palette.skeleton_bg,
                                border_radius=4,
                            ),
                            ft.Container(
                                width=160 - idx * 24,
                                height=16,
                                bgcolor=self.palette.skeleton_bg,
                                border_radius=4,
                            ),
                        ],
                    ),
                )
            )
        self._column.controls = rows
        self.visible = True

    def show_suggestions(
        self,
        raw_input: str,
        suggestions: list[str],
        active_index: int = -1,
    ) -> None:
        """Render ranked suggestions or empty-state prompt."""
        if not raw_input.strip():
            self.hide()
            return

        if not suggestions:
            self._column.controls = [
                ft.Container(
                    padding=ft.Padding(SUGGESTION_PAD_H, 14, SUGGESTION_PAD_H, 14),
                    content=ft.Semantics(
                        label="No suggestions. Press Search to add this word.",
                        content=ft.Text(
                            "No suggestions. Press Search to add this word.",
                            size=15,
                            color=self.palette.muted,
                        ),
                    ),
                )
            ]
            self.visible = True
            return

        prefix_len = bold_prefix_len(raw_input)
        total = len(suggestions)
        rows: list[ft.Control] = []

        for idx, word in enumerate(suggestions):
            is_active = idx == active_index
            bold_part = word[:prefix_len]
            rest_part = word[prefix_len:]

            rank_label = ft.Container(
                width=SUGGESTION_RANK_WIDTH,
                alignment=ft.alignment.center_left,
                content=ft.Text(
                    f"#{idx + 1}",
                    size=SUGGESTION_RANK_SIZE,
                    color=self.palette.muted,
                ),
            )

            word_text = ft.Text(
                spans=[
                    ft.TextSpan(
                        bold_part,
                        style=ft.TextStyle(
                            size=SUGGESTION_TEXT_SIZE,
                            weight=ft.FontWeight.BOLD,
                            color=self.palette.primary,
                        ),
                    ),
                    ft.TextSpan(
                        rest_part,
                        style=ft.TextStyle(
                            size=SUGGESTION_TEXT_SIZE,
                            color=self.palette.text,
                        ),
                    ),
                ],
                expand=True,
                overflow=ft.TextOverflow.ELLIPSIS,
            )

            complete_btn = ft.Semantics(
                label=f"Complete input with {word}",
                button=True,
                content=ft.TextButton(
                    content=ft.Text(
                        "↖ complete",
                        size=12,
                        color=self.palette.muted,
                        weight=ft.FontWeight.W_500,
                    ),
                    height=MIN_TOUCH_TARGET,
                    style=ft.ButtonStyle(
                        padding=ft.Padding(8, 0, 8, 0),
                    ),
                    on_click=lambda _e, w=word: self._on_complete(w),
                ),
            )

            row_container = ft.Container(
                bgcolor=self.palette.suggestion_active if is_active else self.palette.card_bg,
                padding=ft.Padding(SUGGESTION_PAD_H, 2, 8, 2),
                border=ft.Border(
                    bottom=ft.BorderSide(1, self.palette.divider_main)
                )
                if idx < total - 1
                else None,
                content=ft.Row(
                    spacing=SUGGESTION_GAP,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.GestureDetector(
                            expand=True,
                            on_tap=lambda _e, w=word: self._on_select(w),
                            content=ft.Container(
                                padding=ft.Padding(0, SUGGESTION_PAD_V, 0, SUGGESTION_PAD_V),
                                content=ft.Row(
                                    spacing=SUGGESTION_GAP,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[rank_label, word_text],
                                ),
                            ),
                        ),
                        complete_btn,
                    ],
                ),
            )

            rows.append(
                ft.Semantics(
                    label=f"suggestion {idx + 1} of {total}, {word}",
                    button=True,
                    content=row_container,
                )
            )

        self._column.controls = rows
        self.visible = True

    def hide(self) -> None:
        """Collapse suggestion dropdown."""
        self._column.controls = []
        self.visible = False

    def apply_palette(self, palette: ThemePalette) -> None:
        """Update card palette."""
        self.palette = palette
        self.bgcolor = palette.card_bg
