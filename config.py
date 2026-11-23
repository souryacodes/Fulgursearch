"""Application-wide constants for Fulgur Search."""

from __future__ import annotations

APP_NAME: str = "Fulgur Search"
APP_SUBTITLE: str = "Instant search suggestions, ranked"
APP_VERSION: str = "1.0.0"

# Trie and suggestion limits
TOP_K: int = 5
MIN_QUERY_CHARS_HISTORY: int = 2
MIN_QUERY_CHARS_HIGHLIGHT: int = 2

# Pagination and match rendering limits
PAGE_LINES: int = 40
PAGE_CHARS: int = 2600
MAX_HITS: int = 300
VIEWER_RENDER_WINDOW: int = 2  # Render visible page index +/- 2

# File ingestion and validation
MAX_FILE_BYTES: int = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS: tuple[str, ...] = (".txt", ".md", ".csv")
BINARY_CONTROL_RATIO: float = 0.10

# File learning heuristics
WORD_LIST_RATIO: float = 0.80
WORD_LIST_MAX_WORDS: int = 6
PROSE_MAX_TERMS: int = 5000
PROSE_MIN_WORD_LEN: int = 3

# Ranking model (bounded normalized base + personal frequency with recency decay)
BASE_SCORE_CAP: float = 500.0
BASE_NORM_SCALE: float = 100.0
PERSONAL_BASE_FLOOR: float = 1000.0
PERSONAL_FREQ_WEIGHT: float = 100.0
PERSONAL_DECAY_HALF_LIFE_DAYS: float = 14.0

# Undo / UX timings
RESET_UNDO_SECONDS: float = 8.0
PULSE_DURATION_MS: int = 900

# Persistence
DB_FILENAME: str = "fulgur_search.db"
