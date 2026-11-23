# Fulgur Search

Offline trie-based instant autocomplete and local document viewer built in **Python 3.11+** with **Flet** (`flet build apk`) for Android 8+ (API 26+) and desktop.

## Features

- **Instant O(prefix) Top-K Trie (`engine/trie.py`)**: Every node caches its top-5 `(score, word)` pairs for sub-millisecond prefix suggestions, supporting phrase prefixes (`"apple "` vs `"apple"`) and bold matched prefixes.
- **Zero-Hack Ranking (`engine/ranking.py`)**: Bounded normalized base weights (`< 500`) combined with personal search frequency and 14-day half-life recency decay (`>= 1050`), so personal searches always outrank built-ins without arbitrary `1,000,000` multipliers.
- **File Learning (`engine/file_learner.py`)**: Supports `.txt`, `.md`, and `.csv` up to 5 MB. Safely decodes UTF-8 (stripping BOM), UTF-16, CP1252, and Latin-1, rejects binary files, learns word lists (`>= 80%` short lines with optional `,rank`), CSV first columns / `word,rank` pairs, or frequency-ranked prose tokens (`[^\W_][\w'’-]*`, length >= 3, excluding `STOP_WORDS`), with a per-file override toggle.
- **Paginated Viewer & Phrase Matcher (`engine/paginator.py`, `engine/matcher.py`)**: 40-line / 2600-char pages, lazy `±2` page window rendering, single compiled regex per query with Unicode word-boundary default (`(?<![^\W_])`), `"match inside words"` toggle, cross-line phrase highlighting, 300-hit render cap (`"300+ matches (showing first 300)"`), and orange pulse highlight on the active hit.
- **SQLite WAL Persistence (`storage/db.py`)**: Transactional app-private SQLite database with individual search entry deletion and an 8-second undoable Reset.
- **Background Worker (`workers/indexer.py`)**: Decodes, indexes incrementally per document, paginates, and searches off the UI thread via queues.

## Project Layout

```text
config.py             # All numeric, limit, and schema constants
theme.py              # Light/dark palettes, radii, typography, and spacing tokens
main.py               # Flet entry point
pyproject.toml        # Packaging & flet build apk configuration
engine/               # Pure Python (zero UI imports)
  sample_words.py     # Built-in 85 sample words + STOP_WORDS
  trie.py             # __slots__ Node & top-K prefix Trie
  ranking.py          # Normalized base + recency-decayed personal ranking
  file_learner.py     # Decoding, binary validation, word list/CSV/prose learning
  paginator.py        # 40-line / 2600-char pagination
  matcher.py          # Compiled regex phrase matcher across line breaks
storage/
  db.py               # SQLite WAL persistence, transactions, undo snapshots
workers/
  indexer.py          # Background worker thread & result queue
ui/                   # Flet Material 3 UI components & TalkBack Semantics
tests/                # pytest / unittest test suite
```

## Running Tests

```bash
python3 -m pip install -e ".[dev]"
pytest -v
```

Or without pytest (pure stdlib):

```bash
python3 -m unittest discover -s tests -v
```

## Running Locally

```bash
flet run
```

## Building the Android APK (`flet build apk`)

### Prerequisites
- Python **3.11+**
- Flutter SDK (compatible with your installed Flet version) and Android SDK (API 26+ / Android 8.0+)
- Java JDK 17

### Build Steps

1. Create and activate a virtual environment:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install "flet>=0.25.0"
   ```
2. Verify all unit and acceptance tests pass:
   ```bash
   python -m unittest discover -s tests -v
   ```
3. Build the Android APK (no network or API keys required by the app):
   ```bash
   flet build apk --project fulgur-search --org org.fulgursearch --product "Fulgur Search"
   ```
   To build split APKs per ABI for smaller downloads:
   ```bash
   flet build apk --split-per-abi
   ```
4. The installable APK is written to `build/apk/app-release.apk` (or `build/apk/app-arm64-v8a-release.apk` when split). Install on a device via:
   ```bash
   adb install build/apk/app-release.apk
   ```
