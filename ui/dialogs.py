"""Accessible confirmation and file-conflict dialogs for Fulgur Search."""

from __future__ import annotations

from typing import Callable

import flet as ft

from theme import MIN_TOUCH_TARGET, RADIUS_BUTTON, RADIUS_CARD, ThemePalette


def build_confirm_dialog(
    title: str,
    message: str,
    confirm_label: str,
    palette: ThemePalette,
    on_confirm: Callable[[], None],
    on_cancel: Callable[[], None],
    destructive: bool = False,
) -> ft.AlertDialog:
    """Create a generic confirmation dialog with >=48dp touch targets."""
    confirm_color = palette.error_text if destructive else palette.primary
    return ft.AlertDialog(
        modal=True,
        bgcolor=palette.card_bg,
        shape=ft.RoundedRectangleBorder(radius=RADIUS_CARD),
        title=ft.Text(title, color=palette.text, weight=ft.FontWeight.BOLD, size=18),
        content=ft.Text(message, color=palette.muted, size=15),
        actions=[
            ft.TextButton(
                content=ft.Text("Cancel", color=palette.text, size=15),
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                ),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: on_cancel(),
            ),
            ft.FilledButton(
                content=ft.Text(confirm_label, color=palette.on_primary, size=15),
                style=ft.ButtonStyle(
                    bgcolor=confirm_color,
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                ),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: on_confirm(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_duplicate_file_dialog(
    filename: str,
    suggested_alt_name: str,
    palette: ThemePalette,
    on_replace: Callable[[], None],
    on_keep_both: Callable[[], None],
    on_cancel: Callable[[], None],
) -> ft.AlertDialog:
    """Ask user whether to replace an existing same-named file or keep both."""
    return ft.AlertDialog(
        modal=True,
        bgcolor=palette.card_bg,
        shape=ft.RoundedRectangleBorder(radius=RADIUS_CARD),
        title=ft.Text("File already exists", color=palette.text, weight=ft.FontWeight.BOLD, size=18),
        content=ft.Text(
            f'"{filename}" is already loaded. Replace the existing file, or keep both '
            f'and save this one as "{suggested_alt_name}"?',
            color=palette.muted,
            size=15,
        ),
        actions=[
            ft.TextButton(
                content=ft.Text("Cancel", color=palette.muted, size=14),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: on_cancel(),
            ),
            ft.OutlinedButton(
                content=ft.Text("Keep both", color=palette.text, size=14),
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                    side=ft.BorderSide(1, palette.border),
                ),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: on_keep_both(),
            ),
            ft.FilledButton(
                content=ft.Text("Replace", color=palette.on_primary, size=14),
                style=ft.ButtonStyle(
                    bgcolor=palette.primary,
                    shape=ft.RoundedRectangleBorder(radius=RADIUS_BUTTON),
                ),
                height=MIN_TOUCH_TARGET,
                on_click=lambda _: on_replace(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
