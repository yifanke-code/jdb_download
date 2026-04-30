# Debugging: File Explorer Not Showing Files

The file explorer (middle-right table) shows local video files that match an album ID. The app loads data from `c:\github\my_json\my collection.json`.

## The Issue

When you pause on an album, the file list table is empty even though files exist locally.

## Debugging Steps

The code now logs detailed information about each step. Follow these logs:

### 1. Start the app and pause on an album

In the log output (bottom text area), you'll see `[FILES]` messages like:

```
[FILES] Looking for album: JUQ-541 (normalized: JUQ-541)
[FILES] Found 1 matching row(s) for JUQ-541
[FILES]   Path 1: Linux=/volume1/home/admin/Media -> Windows=j:\
[FILES]   ✓ Path exists: j:\
[FILES] Scanning for video files in: j:\
[FILES] Background thread scanning: j:\
[FILES] Thread found 153 files, 27 are video files, 27 to display
[FILES] Successfully displayed 27 file(s) for JUQ-541
```

### 2. Identify where it stops

Check which message appears last:

| Last Message | Problem | Solution |
|---|---|---|
| `Looking for album: ...` | Search completed but no match | Check if album ID is in `my collection.json` |
| `Found N matching row(s)` | Album found but path conversion failed | Check PATH_MAP mappings |
| `Path exists:` | Path OK but files not scanning | Check VIDEO_EXTS filter (line 46) |
| `No video files found` | Files exist but wrong extension | Verify actual file extensions (`.mp4`, `.mkv`, etc.) |
| `Successfully displayed` | Working! | Files should show in the table |

## Common Issues

### Album not found
- **Message**: `Album XXX not found in my collection.json`
- **Fix**: The album ID in the scan doesn't match what's in `my collection.json`
  - Compare: Check exact ID format (spaces, dashes, case)
  - Update: Add the missing ID to `my collection.json`

### Path not found  
- **Message**: `Path not found: j:\` (or similar)
- **Fix**: The Windows path doesn't exist
  - Edit `PATH_MAP` in `jdb_download.py` (line 50-55)
  - Ensure Linux path → Windows path mapping is correct

### No video files found
- **Message**: `Thread found 100 files, 0 are video files`
- **Fix**: Files exist but don't match the video extension filter
  - Check actual file extensions: `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`
  - Update `VIDEO_EXTS` on line 46 if needed

## PATH_MAP Configuration

Your current PATH_MAP should map Linux paths from `my collection.json` to Windows:

```python
PATH_MAP = {
    '/volume1/aria2':         'w:/',                  
    '/volume2/Media_on':      'g:/',
    '/volume1/home/admin/18': 'p:/18',
    '/volume1/home/admin/Media': 'j:/',
}
```

When a path in `my collection.json` is `/volume1/home/admin/Media/JUQ-541`, it converts to `j:\JUQ-541`.

## Next Steps

1. **Run the app** and pause on any album
2. **Check the logs** for `[FILES]` messages  
3. **Share the output** showing where it stops
4. I can help fix the specific issue
