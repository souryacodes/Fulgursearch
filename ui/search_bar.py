"""Header, search input bar, live status timing, and search result summary card."""

from __future__ import annotations

from typing import Callable

import flet as ft

from config import APP_SUBTITLE
from theme import (
    INPUT_SIZE,
    MIN_TOUCH_TARGET,
    RADIUS_BUTTON,
    RADIUS_CARD,
    RADIUS_INPUT,
    RESULT_PAD,
    SUBTITLE_SIZE,
    TITLE_LETTER_SPACING,
    TITLE_SIZE,
    ThemePalette,
)


class SearchHeader(ft.Column):
    """Top brand title, search input row (no launch autofocus), status, and result card."""

    def __init__(
        self,
        palette: ThemePalette,
        on_query_change: Callable[[str], None],
        on_submit_search: Callable[[str], None],
    ) -> None:
        super().__init__(spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.palette = palette
        self._on_query_change = on_query_change
        self._on_submit_search = on_submit_search

        self.title_text = ft.Text(
            spans=[
                ft.TextSpan(
                    "Fulgur ",
                    style=ft.TextStyle(
                        size=TITLE_SIZE,
                        weight=ft.FontWeight.BOLD,
                        letter_spacing=TITLE_LETTER_SPACING,
                        color=palette.text,
                    ),
                ),
                ft.TextSpan(
                    "Search",
                    style=ft.TextStyle(
                        size=TITLE_SIZE,
                        weight=ft.FontWeight.BOLD,
                        letter_spacing=TITLE_LETTER_SPACING,
                        color=palette.primary,
                    ),
                ),
            ],
            text_align=ft.TextAlign.CENTER,
        )

        self.subtitle_text = ft.Text(
            APP_SUBTITLE,
            size=SUBTITLE_SIZE,
            color=palette.muted,
            text_align=ft.TextAlign.CENTER,
        )

        self.query_input = ft.TextField(
            value="",
            autofocus=False,
            hint_text='Start typing... (try "a")',
            hint_style=ft.TextStyle(color=palette.muted, size=INPUT_SIZE),
            text_style=ft.TextStyle(color=palette.text, size=INPUT_SIZE),
            bgcolor=palette.card_bg,
            border_color=palette.border,
            focused_border_color=palette.primary,
            border_width=2,
            focused_border_width=2,
            border_radius=RADIUS_INPUT,
            content_padding=ft.Padding(16, 14, 16, 14),
            keyboard_type=ft.KeyboardType.TEXT,
            expand=True,
            on_change=self._handle_change,
            on_submit=self._handle_submit,
        )

        self.search_button = ft.FilledButton(
            content=ft.Text("Search", size=16, weight=ft.FontWeight.W_600, color=palette.on_primary),
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT: palette.primary,
                    ft.ControlState.PRESSED: palette.primary_pressed,
                    ft.ControlState.HOVERED: palette.primary_pressed,
                },
                shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                padding=ft.Padding(20, 0, 20, 0),
            ),
            height=54,
            on_click=self._handle_button_click,
        )

        self.input_row = ft.Row(
            controls=[
                ft.Semantics(
                    label="Search query input",
                    hint="Type to see instant ranked suggestions",
                    text_field=True,
                    content=self.query_input,
                ),
                ft.Semantics(
                    label="Search",
                    button=True,
                    content=self.search_button,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.status_text = ft.Text(
            "",
            size=13,
            color=palette.muted,
        )
        self.status_box = ft.Container(
            content=ft.Semantics(live_region=True, content=self.status_text),
            padding=ft.Padding(4, 8, 4, 4),
            visible=False,
        )

        self.result_heading = ft.Text("", size=18, weight=ft.FontWeight.BOLD, color=palette.text)
        self.result_body = ft.Text("", size=15, color=palette.muted)
        self.result_card = ft.Container(
            visible=False,
            bgcolor=palette.card_bg,
            border_radius=RADIUS_CARD,
            padding=RESULT_PAD,
            margin=ft.Margin(0, 10, 0, 0),
            shadow=ft.BoxShadow(
                blur_radius=10,
                spread_radius=0,
                color="#0F000000",
                offset=ft.Offset(0, 2),
            ),
            content=ft.Semantics(
                live_region=True,
                content=ft.Column(
                    controls=[self.result_heading, self.result_body],
                    spacing=6,
                ),
            ),
        )

        self.controls = [
            ft.Container(content=self.title_text, alignment=ft.alignment.center),
            ft.Container(
                content=self.subtitle_text,
                alignment=ft.alignment.center,
                margin=ft.Margin(0, 6, 0, 22),
            ),
            self.input_row,
            self.status_box,
        ]

    def _handle_change(self, e: ft.ControlEvent) -> None:
        self._on_query_change(e.control.value or "")

    def _handle_submit(self, e: ft.ControlEvent) -> None:
        self._on_submit_search(self.query_input.value or "")

    def _handle_button_click(self, _e: ft.ControlEvent) -> None:
        self._on_submit_search(self.query_input.value or "")

    def set_input_value(self, text: str) -> None:
        """Update the search field programmatically without firing search."""
        self.query_input.value = text

    def set_status(self, message: str) -> None:
        """Update timing/status line below suggestions."""
        self.status_text.value = message
        self.status_box.visible = bool(message)

    def show_result(self, heading: str, body: str) -> None:
        """Show the search feedback summary card."""
        self.result_heading.value = heading
        self.result_body.value = body
        self.result_card.visible = True

    def clear_result(self) -> None:
        """Hide stale search result summary card."""
        self.result_heading.value = ""
        self.result_body.value = ""
        self.result_card.visible = False

    def apply_palette(self, palette: ThemePalette, compact: bool = False) -> None:
        """Refresh colors and responsive heading size."""
        self.palette = palette
        title_sz = 34 if compact else TITLE_SIZE
        self.title_text.spans[0].style = ft.TextStyle(
            size=title_sz,
            weight=ft.FontWeight.BOLD,
            letter_spacing=TITLE_LETTER_SPACING,
            color=palette.text,
        )
        self.title_text.spans[1].style = ft.TextStyle(
            size=title_sz,
            weight=ft.FontWeight.BOLD,
            letter_spacing=TITLE_LETTER_SPACING,
            color=palette.primary,
        )
        self.subtitle_text.color = palette.muted
        self.query_input.bgcolor = palette.card_bg
        self.query_input.border_color = palette.border
        self.query_input.focused_border_color = palette.primary
        self.query_input.text_style = ft.TextStyle(color=palette.text, size=INPUT_SIZE)
        self.query_input.hint_style = ft.TextStyle(color=palette.muted, size=INPUT_SIZE)
        self.search_button.style = ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: palette.primary,
                ft.ControlState.PRESSED: palette.primary_pressed,
                ft.ControlState.HOVERED: palette.primary_pressed,
            },
            shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
            padding=ft.Padding(16 if compact else 20, 0, 16 if compact else 20, 0),
        )
        self.status_text.color = palette.muted
        self.result_card.bgcolor = palette.card_bg
        self.result_heading.color = palette.text
        self.result_body.color = palette.muted
        self.search_button.height = max(MIN_TOUCH_TARGET, 52 if compact else 54)
