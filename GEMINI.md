# JAV DB Downloader - Project Context

## Project Overview
JAV DB Downloader is a comprehensive PyQt6 desktop application designed to browse JavDB.com, extract video metadata and magnet links, and facilitate downloads through aria2 or PikPak. It features a sophisticated scanning engine using Playwright (via Chrome DevTools Protocol) to navigate the site while mimicking human behavior to avoid detection.

### Core Technologies
- **UI Framework:** PyQt6
- **Web Automation:** Playwright (sync API) with Chrome Remote Debugging
- **Parsing:** BeautifulSoup4 and pre-compiled Regular Expressions
- **Data Management:** Pandas DataFrames backed by JSON files for local metadata caching
- **Downloads:** `aria2p` for aria2 RPC and `pikpakapi` for PikPak integration

### Key Files
- `jdb_download.py`: The main entry point containing the `JdbDownloader` class (UI and orchestration) and `AlbumInfo` (domain model).
- `get_pikpak_token.py`: Helper script for obtaining and managing PikPak authentication tokens.
- `find_javdb_legend.py`: Utility script for searching specific JavDB content.
- `my javdb.json`: Local database of album metadata.
- `my collection.json`: Inventory of locally available files.
- `maglink_added.json`: History of downloaded magnet links to prevent duplicates.

---

## Building and Running

### Prerequisites
- **Python:** 3.11 or higher
- **OS:** Windows (optimized for Windows file paths and VLC integration)
- **External:** Chrome browser must be installed.

### Environment Setup
```bash
pip install pandas pyperclip beautifulsoup4 playwright aria2p pikpakapi PyQt6
playwright install chromium
```

### Execution Steps
1. **Start Chrome with Remote Debugging:**
   This is mandatory as the app connects to an existing browser instance to leverage existing sessions/cookies.
   ```bash
   chrome --remote-debugging-port=9222
   ```
2. **Launch the Application:**
   ```bash
   python jdb_download.py
   ```

---

## Architecture & Development Conventions

### High-Level Flow
The application follows a **Research -> User Decision -> Execution** pattern:
1. **Fetch:** Playwright navigates JavDB.
2. **Parse:** Content is extracted using efficient module-level regexes and BeautifulSoup.
3. **Filter:** Automated filters (-nl, -nc, -uc, -4k) narrow down results.
4. **Display:** Metadata is shown in the PyQt6 UI for manual review.
5. **Act:** User triggers downloads or skips; data is persisted to JSON.

### Domain Models
- `AlbumInfo`: A `__slots__` based class representing a single video entry. It includes metadata like ID, title, actors, release date, and magnet links.

### Performance & Safety
- **O(1) Lookups:** High-speed filtering uses sets (`downloaded_maglinks`, `id_list`, etc.) synced with Pandas DataFrames.
- **Anti-Detection:** Uses random delays (`my_delay()`) and specific browser headers.
- **Security Check:** `check_security_verification()` detects Cloudflare/CAPTCHA challenges.

### Threading Guidelines
- **UI Thread Safety:** All long-running tasks (scans, network requests) must run in background threads (e.g., `LocalScanWorker`).
- **Callbacks:** Use `QTimer.singleShot(0, ...)` or signals to update the UI from worker threads.
- **Logging:** `self.log()` is the centralized, thread-safe method for outputting to the UI text widget.

### Path Mapping
The app handles cross-platform path mapping via `PATH_MAP`, typically translating Linux-style NAS paths (e.g., `/volume1/...`) to Windows drive letters (e.g., `W:/`).

---

## Troubleshooting

### Local File Explorer Issues
If the file explorer (middle-right table) is empty when it should show local files:
1. **Check Logs:** Look for `[FILES]` tags in the application log.
2. **Verify `my collection.json`:** Ensure the album ID exists in the collection database.
3. **Path Mapping:** Verify that `PATH_MAP` in `jdb_download.py` correctly translates the Linux path from the JSON to a valid Windows drive/path.
4. **File Extensions:** Ensure video files match the extensions in `VIDEO_EXTS` (e.g., `.mp4`, `.mkv`).

### Browser Connection
- Ensure Chrome is launched with `--remote-debugging-port=9222`.
- If the app hangs on `safe_goto`, check if the browser has a Cloudflare challenge or is unresponsive.

### Data Persistence
- If changes aren't saving, verify the application has write permissions to the JSON files (especially if they are located in `c:/github/my_json`).
