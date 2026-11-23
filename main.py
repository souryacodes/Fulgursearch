"""Entry point for Fulgur Search Flet Android & desktop application."""

from __future__ import annotations

import flet as ft

from ui.app import FulgurSearchApp


def main(page: ft.Page) -> None:
    """Initialize and mount the Fulgur Search UI."""
    FulgurSearchApp(page)


if __name__ == "__main__":
    ft.app(target=main)
