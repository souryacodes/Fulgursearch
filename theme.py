"""Design tokens, colors, dimensions, and light/dark palettes for Fulgur Search."""

from __future__ import annotations

from dataclasses import dataclass


# Core Light Palette (brand identity)
BG: str = "#f4f6fb"
TEXT: str = "#1d2433"
PRIMARY: str = "#2f6fed"
PRIMARY_PRESSED: str = "#2559c4"
MUTED: str = "#6b7487"
BORDER: str = "#d5dbe8"
LIGHT_BTN: str = "#e6eaf4"
LIGHT_BTN_PRESSED: str = "#d5dbe8"
SUGGESTION_ACTIVE: str = "#eaf1ff"
DIVIDER_MAIN: str = "#eef0f6"
DIVIDER_SOFT: str = "#f3f4f9"
LINE_NO: str = "#b0b7c9"
HIT_BAR_BG: str = "#fff9e0"
HIT_BAR_BORDER: str = "#f1e6b4"
HIT_PRESSED: str = "#f4f7ff"
HIT_SELECTED: str = "#fff1c9"
HIGHLIGHT_BG: str = "#ffe27a"
BADGE_BG: str = "#ffe27a"
CURRENT_MATCH_BG: str = "#ff9f43"
CURRENT_MATCH_OUTLINE: str = "#ff7a00"
TOP_LIST_TEXT: str = "#444c5e"
VIEWER_BG: str = "#e9edf6"
WHITE: str = "#ffffff"
CARD_BG: str = "#ffffff"
SKELETON_BG: str = "#e3e8f4"
ERROR_TEXT: str = "#b91c1c"
WARNING_BG: str = "#fff4e5"
WARNING_BORDER: str = "#f59e0b"
WARNING_TEXT: str = "#7c2d12"

# Radii
RADIUS_CARD: int = 10
RADIUS_INPUT: int = 10
RADIUS_BUTTON: int = 10
RADIUS_TAB: int = 8
RADIUS_PAGE: int = 4
RADIUS_MARK: int = 3
RADIUS_BADGE: int = 9

# Layout & Typography Metrics
MAX_CONTENT_WIDTH: int = 760
PAGE_CARD_MAX_WIDTH: int = 580
VIEWER_HEIGHT: int = 440
HITS_MAX_HEIGHT: int = 150
GUTTER_WIDTH: int = 34
MIN_TOUCH_TARGET: int = 48

TITLE_SIZE: int = 44
TITLE_LETTER_SPACING: float = -1.0
SUBTITLE_SIZE: int = 15
INPUT_SIZE: int = 18
SUGGESTION_TEXT_SIZE: int = 17
SUGGESTION_RANK_SIZE: int = 13
SUGGESTION_RANK_WIDTH: int = 26
SUGGESTION_GAP: int = 12
SUGGESTION_PAD_V: int = 11
SUGGESTION_PAD_H: int = 16
RESULT_PAD: int = 16
VIEWER_PAD: int = 14


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Resolved theme tokens supporting light (default) and system dark modes."""

    bg: str
    card_bg: str
    text: str
    primary: str
    primary_pressed: str
    on_primary: str
    muted: str
    border: str
    light_btn: str
    light_btn_pressed: str
    suggestion_active: str
    divider_main: str
    divider_soft: str
    line_no: str
    hit_bar_bg: str
    hit_bar_border: str
    hit_pressed: str
    hit_selected: str
    highlight_bg: str
    highlight_text: str
    badge_bg: str
    badge_text: str
    current_match_bg: str
    current_match_outline: str
    top_list_text: str
    viewer_bg: str
    skeleton_bg: str
    error_text: str
    warning_bg: str
    warning_border: str
    warning_text: str


LIGHT_PALETTE = ThemePalette(
    bg=BG,
    card_bg=CARD_BG,
    text=TEXT,
    primary=PRIMARY,
    primary_pressed=PRIMARY_PRESSED,
    on_primary=WHITE,
    muted=MUTED,
    border=BORDER,
    light_btn=LIGHT_BTN,
    light_btn_pressed=LIGHT_BTN_PRESSED,
    suggestion_active=SUGGESTION_ACTIVE,
    divider_main=DIVIDER_MAIN,
    divider_soft=DIVIDER_SOFT,
    line_no=LINE_NO,
    hit_bar_bg=HIT_BAR_BG,
    hit_bar_border=HIT_BAR_BORDER,
    hit_pressed=HIT_PRESSED,
    hit_selected=HIT_SELECTED,
    highlight_bg=HIGHLIGHT_BG,
    highlight_text=TEXT,
    badge_bg=BADGE_BG,
    badge_text=TEXT,
    current_match_bg=CURRENT_MATCH_BG,
    current_match_outline=CURRENT_MATCH_OUTLINE,
    top_list_text=TOP_LIST_TEXT,
    viewer_bg=VIEWER_BG,
    skeleton_bg=SKELETON_BG,
    error_text=ERROR_TEXT,
    warning_bg=WARNING_BG,
    warning_border=WARNING_BORDER,
    warning_text=WARNING_TEXT,
)

DARK_PALETTE = ThemePalette(
    bg="#111622",
    card_bg="#1a2234",
    text="#eef2ff",
    primary="#5a90ff",
    primary_pressed="#4078eb",
    on_primary="#0b1120",
    muted="#9aa5be",
    border="#2f3b54",
    light_btn="#253047",
    light_btn_pressed="#32405e",
    suggestion_active="#243456",
    divider_main="#27324a",
    divider_soft="#202a3f",
    line_no="#6e7a96",
    hit_bar_bg="#2d2718",
    hit_bar_border="#594a22",
    hit_pressed="#26334d",
    hit_selected="#433818",
    highlight_bg="#ffe27a",
    highlight_text="#1d2433",
    badge_bg="#ffe27a",
    badge_text="#1d2433",
    current_match_bg="#ff9f43",
    current_match_outline="#ff7a00",
    top_list_text="#cbd5e1",
    viewer_bg="#141b2a",
    skeleton_bg="#263149",
    error_text="#f87171",
    warning_bg="#332211",
    warning_border="#d97706",
    warning_text="#fde68a",
)


def get_palette(is_dark: bool) -> ThemePalette:
    """Return the active theme palette."""
    return DARK_PALETTE if is_dark else LIGHT_PALETTE
