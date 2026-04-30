# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

JAV DB Downloader is a PyQt6 desktop application that browses JavDB.com, extracts video metadata and magnet links, and facilitates downloads via aria2 or PikPak. It includes local file scanning, metadata caching in JSON, and clipboard monitoring for automated magnet detection.

## Running the Application

### Prerequisites
- Python 3.11+
- Windows OS
- Chrome browser with remote debugging enabled
- Required packages: `pandas`, `pyperclip`, `beautifulsoup4`, `playwright`, `aria2p`, `pikpakapi`, `PyQt6`

### Installation
```bash
pip install pandas pyperclip beautifulsoup4 playwright aria2p pikpakapi PyQt6
playwright install chromium
```

### Startup
1. **Start Chrome with debugging** (separate terminal):
   ```bash
   chrome --remote-debugging-port=9222
   ```

2. **Run the application**:
   ```bash
   python jdb_download.py
   ```

## Architecture

### High-Level Flow
```
Chrome (CDP) ← Playwright ← Main Window (PyQt6)
                   ↓
              Page Parser (BeautifulSoup)
                   ↓
            AlbumInfo (domain model)
                   ↓
         JSON files ← Pandas DataFrame
                   ↓
        aria2/PikPak download
```

### Key Components

**jdb_download.py** (main file)
- `JdbDownloader`: PyQt6 main window, orchestrates the entire UI and workflow
- `AlbumInfo`: Domain model representing a single album/video with metadata
- `LocalScanWorker`: Background worker for scanning local files against JavDB database
- Regex patterns: Pre-compiled patterns for efficient HTML parsing
- Helper functions: Browser navigation, HTML parsing, path conversion, data serialization

### Data Layer

**In-Memory DataFrames** (synced with JSON files)
- `df_maglink`: Tracks downloaded magnet links (maglink_added.json)
- `df_javdb`: Album database (my javdb.json)
- `df_collection`: Local file inventory (my collection.json)
- `df_check`: Recently checked albums (check.json)

**Fast-Lookup Sets** (kept in sync with DataFrames)
- `downloaded_maglinks`: Set of downloaded magnet IDs
- `id_list`: Set of known album IDs
- `collection_ids`: Set of collection album IDs
- `check_list`: Set of album IDs in collection
- `checked_ids`: Set of recently checked album IDs

All lookups in filtering/skip logic use these sets for O(1) performance. When adding to a DataFrame, update the corresponding set.

### UI Structure (PyQt6)

**Main sections** (in _init_ui):
1. **Page Range**: Select all pages, single page, or range (to/from spinboxes)
2. **Search URL**: Choose search type (censored, uncensored, search, actor), set custom URL, resume ID
3. **Direct Album Link**: Load a specific album by URL
4. **Local File Scan**: Browse and scan local video folder
5. **Filters**: -nl (old films only), -nc (solo only), -fda (force redownload), -uc (uncensored/subtitle), -4k (4K only)
6. **Destination**: Choose aria2 or PikPak for downloads
7. **Album Display**: Two tables side-by-side
   - Left: Magnet links with sorting (uncensored > subtitle > HD > size > date)
   - Right: Local files in the album folder (with play/delete options)
8. **Control Buttons**: Continue, Skip, Save to W:/, STOP
9. **Log Output**: Text widget showing all operations

### Scan Workflow

**Main scan loop** (process_page → process_album)
1. Fetch page from JavDB with Playwright
2. Extract album links via regex `RE_PAGE_LINKS`
3. For each album:
   - Apply resume ID filter (skip until resume ID is found)
   - Apply collection/date/magnet filters
   - Load album page and parse metadata (actors, series, tags, rating)
   - Apply actor count filter (-nc)
   - Parse magnet items with BeautifulSoup
   - Apply uncensored/4K filters (-uc, -4k)
   - Display album info and pause for user decision
4. User chooses: Continue, Skip, or Download
5. Move to next album

**Local file scan** (LocalScanWorker)
- Extracts video ID from filename via regex patterns
- Searches JavDB for extracted ID
- Loads album page and parses metadata
- Runs in background thread with progress callback
- Flushes to JSON every N albums (SAVE_EVERY = 4)

### Key Regex Patterns

**HTML parsing**:
- `RE_ALBUM_LINKS`: Album page URLs from listing
- `RE_ITEM_ORIGIN`/`RE_ITEM_CURRENT`: Album ID and title
- `RE_ACTORS`: Actress links and names
- `RE_SERIES`/`RE_TAGS`: Series and tag names
- `RE_RATES`/`RE_RELEASES`: Ratings and release dates
- `RE_IMG_LINKS`: Cover image URLs
- `RE_PAGE_LINKS`: Full album metadata from listing page

**Data extraction**:
- `RE_ID_PATTERNS`: Extract video ID from filenames (matches patterns like "ABC-123", "AB123")
- `RE_MAGNET`: Extract magnet links from any text
- `RE_JAVDB_ALBUM`: Extract JavDB album URLs
- `RE_SECURITY`: Detect cloudflare/security verification pages

### Configuration

**Network**:
- `ARIA2_SERVER`: aria2 RPC server address (default: 192.168.50.7:6800)
- `PIKPAK_TOKEN`: Loaded from `pikpak_token.db` if exists

**Paths**:
- `PATH_MAP`: Dictionary mapping Linux paths to Windows drive letters (used by file explorer)
- `MAGLINK_FN`, `JAVDB_FN`, `COLLECTION_FN`, `CHECK_FN`: JSON file paths (local dir first, fallback to c:/github/my_json)

**Timing**:
- `DELAYS`: Random delays for each request (to avoid detection)
- `my_delay()`: Pick random delay from DELAYS list

**Video extensions**: `VIDEO_EXTS` frozenset for file filtering

## Common Development Tasks

### Adding a New Filter
1. Add a checkbox in `_init_ui()` (in Filters section)
2. Check the checkbox state in `process_album()` before display
3. Log skip reason with `self.log(f'[SKIP] {aid} filter reason')`

### Modifying Album Data Fields
1. Update `AlbumInfo` class `__slots__`
2. Update `parse_album_page()` return dict if parsing new HTML
3. Update `add_album_to_memory()` to save to DataFrame
4. Update UI display in `display_album_info()` if user-facing

### Fixing Parse Issues
- Pre-compiled regexes are at module level (compile once, reuse everywhere)
- Use BeautifulSoup for DOM-based parsing (magnet items)
- Test regex patterns against actual HTML samples
- Log parse failures with enough context (which regex, what input)

### Thread Safety
- All UI updates must go through `QTimer.singleShot(0, ...)` from worker threads
- Logging via `self.log()` is thread-safe (checks main thread and re-routes)
- DataFrame operations in main thread only

### Adding a New Download Method
1. Create API client in `__init__()` (like `self.aria2` or `self.pikpak`)
2. Add radio button or dropdown option in UI
3. Implement in `on_table_double_click()` and clipboard handlers
4. Append magnet to `df_maglink` via `_append_maglink()`

## File Organization

```
jdb_download.py          # Main application (1590 lines)
copy_2_aj_form.py        # Supporting utilities (form handling?)
copy_2_aj_ui.py          # Supporting utilities (UI helpers?)
find_javdb_legend.py     # Utility script
get_pikpak_token.py      # Token generation helper
pikpak_token.db          # PikPak auth token (SQLite or JSON)
my javdb.json            # Album database (persistent)
my collection.json       # Local file inventory (persistent)
maglink_added.json       # Downloaded magnet links (persistent)
check.json               # Recently checked albums (persistent)
error.log                # Error logging
```

## Important Notes

- **No blocking calls in UI thread**: Use `QTimer.singleShot()` for async operations
- **Browser connection**: Requires Chrome with `--remote-debugging-port=9222` running
- **Path conversion**: Linux paths (from mounted NAS) convert to Windows drive letters via `PATH_MAP`
- **Resume ID**: Allows skipping to a specific album ID during scan
- **Recently checked warning**: Warns if an album was checked within 10 days (tracked in `df_check`)
- **Clipboard monitoring**: Automatically detects magnet links and JavDB URLs while scanning
- **Local file play**: Uses VLC if installed, falls back to system default player
- **Token persistence**: PikPak token stored in `pikpak_token.db` and reloaded on startup

## Testing / Verification

When making changes:
- Verify regex patterns against real JavDB HTML (test `safe_goto()` + regex)
- Check DataFrame operations preserve column structure and types
- Ensure new filters don't break existing filter combinations
- Test clipboard detection with actual magnet links in clipboard
- Verify local file scan finds and matches video files correctly
