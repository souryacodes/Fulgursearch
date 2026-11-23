"""Bottom section: file/word stats, reset button, reduce-animations toggle, and top searches."""

from __future__ import annotations

from typing import Callable

import flet as ft

from engine.ranking import SearchRecord
from engine.sample_words import SAMPLE_WORDS
from theme import MIN_TOUCH_TARGET, RADIUS_BUTTON, ThemePalette


class HistorySection(ft.Container):
    """Bottom section displaying learned data summary, reset control, and top 5 searches."""

    def __init__(
        self,
        palette: ThemePalette,
        on_reset_clicked: Callable[[], None],
        on_delete_search: Callable[[str], None],
        on_toggle_reduce_animations: Callable[[bool], None],
    ) -> None:
        self.palette = palette
        self._on_reset_clicked = on_reset_clicked
        self._on_delete_search = on_delete_search
        self._on_toggle_reduce_animations = on_toggle_reduce_animations

        self.reset_btn = ft.Semantics(
            label="Reset learned data",
            button=True,
            content=ft.FilledTonalButton(
                content=ft.Text("Reset learned data", size=14, color=palette.text),
                style=ft.ButtonStyle(
                    bgcolor={
                        ft.ControlState.DEFAULT: palette.light_btn,
                        ft.ControlState.PRESSED: palette.light_btn_pressed,
                    },
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                    padding=ft.Padding(14, 0, 14, 0),
                ),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: self._on_reset_clicked(),
            ),
        )

        self.reduce_anim_switch = ft.Switch(
            value=False,
            label="Remove animations",
            label_position=ft.LabelPosition.LEFT,
            active_color=palette.primary,
            on_change=lambda e: self._on_toggle_reduce_animations(bool(e.control.value)),
        )

        self.help_text = ft.Text(
            'Add .txt, .md or .csv files with the button above. Each file is shown page by page, '
            'and its words become suggestions. A word-list file can give a starting rank after a comma, '
            'e.g. "python tutorial,5". Lines starting with # are shown but not learned.',
            size=13,
            color=palette.muted,
        )
        self.info_text = ft.Text("", size=14, color=palette.text)
        self.top_list_col = ft.Column(spacing=4)

        super().__init__(
            margin=ft.Margin(0, 32, 0, 16),
            padding=ft.Padding(0, 18, 0, 0),
            border=ft.Border(top=ft.BorderSide(1, palette.border)),
            content=ft.Column(
                spacing=10,
                cross_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Text("Your files and words", size=16, weight=ft.FontWeight.BOLD, color=palette.text),
                    ft.Row(
                        spacing=12,
                        wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.reset_btn,
                            ft.Semantics(
                                label="Remove animations accessibility toggle",
                                content=self.reduce_anim_switch,
                            ),
                        ],
                    ),
                    self.help_text,
                    ft.Semantics(live_region=True, content=self.info_text),
                    ft.Container(
                        margin=ft.Margin(0, 8, 0, 0),
                        content=ft.Text(
                            "Your most searched",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=palette.text,
                        ),
                    ),
                    self.top_list_col,
                ],
            ),
        )
        self.update_stats(doc_count=0, records=[])

    def update_stats(
        self,
        doc_count: int,
        records: list[SearchRecord],
        extra_note: str = "",
        reduce_animations: bool | None = None,
    ) -> None:
        """Refresh file/word info summary and top-5 deletable search history list."""
        if reduce_animations is not None:
            self.reduce_anim_switch.value = reduce_animations

        base_msg = f"{len(SAMPLE_WORDS)} sample words + {doc_count} file(s) you added."
        self.info_text.value = f"{base_msg} {extra_note}".strip()

        top5 = sorted(records, key=lambda r: (-r.count, -r.last_searched_at, r.word))[:5]
        if not top5:
            self.top_list_col.controls = [
                ft.Text(
                    "Nothing yet. Search a word and tap Search.",
                    size=14,
                    color=self.palette.muted,
                )
            ]
            return

        rows: list[ft.Control] = []
        for idx, rec in enumerate(top5, start=1):
            del_btn = ft.Semantics(
                label=f"Delete {rec.word} from search history",
                button=True,
                content=ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=18,
                    icon_color=self.palette.muted,
                    width=MIN_TOUCH_TARGET,
                    height=MIN_TOUCH_TARGET,
                    tooltip=f"Remove {rec.word}",
                    on_click=lambda _e, w=rec.word: self._on_delete_search(w),
                ),
            )
            rows.append(
                ft.Container(
                    padding=ft.Padding(8, 0, 4, 0),
                    border=ft.Border(bottom=ft.BorderSide(1, self.palette.divider_soft)),
                    content=ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                f"{idx}. {rec.word} ({rec.count}x)",
                                size=15,
                                color=self.palette.top_list_text,
                                expand=True,
                            ),
                            del_btn,
                        ],
                    ),
                )
            )
        self.top_list_col.controls = rows

    def apply_palette(self, palette: ThemePalette) -> None:
        self.palette = palette
        self.border = ft.Border(top=ft.BorderSide(1, palette.border))
        self.help_text.color = palette.muted
        self.info_text.color = palette.text
