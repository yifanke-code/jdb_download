#!/usr/bin/env python3
# coding=utf-8
import os
import subprocess
import asyncio
import re
import sys
import time
import random
import shutil
import threading
from pathlib import Path
from datetime import datetime

import json
import pandas as pd
import pyperclip
import signal
from playwright.sync_api import sync_playwright
import aria2p
from pikpakapi import PikPakApi

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QGroupBox, QTextEdit,
    QComboBox, QSpinBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QRadioButton, QFileDialog,
)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QTextCursor

# ─── Configuration ────────────────────────────────────────────────────────────

ARIA2_SERVER = 'http://192.168.50.7'

PIKPAK_TOKEN = ''
TOKEN_FILE = Path(__file__).parent / 'pikpak_token.db'
if TOKEN_FILE.exists():
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
            PIKPAK_TOKEN = token_data.get('encoded_token', '')
    except Exception:
        pass
DELAYS = [10, 1, 3, 7, 2, 0.2, 18, 3, 6, 15, 5, 0.5, 0.1, 1, 6, 4, 2, 8, 12]
VIDEO_EXTS = frozenset({'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'})
VIDEO_EXT_RE = re.compile(r'\.(MP4|MKV|AVI|MOV|WMV|FLV|WEBM|M4V|PRORES)$')
JUNK_RE = re.compile(r'HHD800(?:\.COM)?|KCF9(?:\.COM)?|@\s*')

PATH_MAP = {
    '/volume1/aria2':         'w:/',
    '/volume2/Media_on':      'g:/',
    '/volume1/home/admin/18': 'p:/18',
    '/volume1/home/admin/Media': 'j:/',
}

# Pre-compiled regexes used in parsing (compiled once, reused everywhere)
RE_ALBUM_LINKS   = re.compile(r'<a\s{1}href="(/v/[0-9A-Za-z]+)"')
RE_ITEM_CURRENT  = re.compile(r'video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class="current-title">([^<]+)<')
RE_ITEM_ORIGIN   = re.compile(r'video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class="origin-title">([^<]+)<')
RE_ACTORS        = re.compile(r'<a\s{1}href="/actors/([^"]+)[^>]+>([^<]+)</a><strong\sclass="symbol\sfemale">')
RE_SERIES        = re.compile(r'<a\shref="/series[^>]+>([^<]+)')
RE_TAGS          = re.compile(r'<a\shref="/tags[^>]+>([^<]+)')
RE_RATES         = re.compile(r'(?<=&nbsp;)[0-9.]+(?=分)')
RE_RELEASES      = re.compile(r'日期:[\w\W]+?class="value">([^<]+)</span>')
RE_IMG_LINKS     = re.compile(r'class="video-meta-panel"[\w\W]+?<img\ssrc="([^"]+)"\sclass="video-cover"')
RE_PAGE_LINKS    = re.compile(
    r'<a\s{1}href="([^"]+(?="\sclass="box")).+?((?<=<strong>)[^<]+)</stron.+?'
    r'<div\sclass="meta">\n\s+([^\n]+).+?((?<=<div\sclass="tags\shas-addons">).+?(?=</div>))',
    re.DOTALL
)
RE_SECURITY      = re.compile(
    r'Security\s*Verification|驗證.*您的|robot\s*check|cloudflare.*challenge'
    r'|Access\s+denied|Google\s*Recaptcha|cf.*verify|turnstile',
    re.IGNORECASE
)
RE_MAGNET        = re.compile(r'magnet:\?[^\s\n]+')
RE_JAVDB_ALBUM   = re.compile(r'https://javdb\.com/v/[0-9A-Za-z]+')
RE_ITEM_DIV      = re.compile(r'<div\s+class="item\s+[^"]*">([\s\S]*?)(?=<div\s+class="item|$)', re.DOTALL)
RE_ID_PATTERNS   = [
    re.compile(r'([A-Z]{2,5}[-\s]?\d{3,5})'),
    re.compile(r'([A-Z]{1,2}\d{2,5})'),
    re.compile(r'([A-Z]+\d+)'),
]

# ─── File paths ───────────────────────────────────────────────────────────────

def get_json_path(filename: str, fallback_dir: str = 'c:/github/my_json') -> Path:
    local = Path(f'./{filename}')
    fallback = Path(f'{fallback_dir}/{filename}')
    if local.exists():
        return local
    elif fallback.exists():
        return fallback
    else:
        # Return fallback path so user can see where it should be
        return fallback

MAGLINK_FN    = get_json_path('maglink_added.json')
JAVDB_FN      = get_json_path('my javdb.json')
COLLECTION_FN = get_json_path('my collection.json')
CHECK_FN      = get_json_path('check.json')

# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_df(fn: Path, columns: list | None = None) -> pd.DataFrame:
    if fn.is_file():
        try:
            return pd.read_json(fn)
        except Exception:
            pass
    return pd.DataFrame(columns=columns) if columns else pd.DataFrame()

def save_df(df: pd.DataFrame, fn: Path) -> None:
    try:
        df.reset_index(drop=True, inplace=True)
        df.to_json(fn, index=False)
    except Exception as e:
        print(f'Cannot write to {fn}: {e}')

# ─── Browser helpers ──────────────────────────────────────────────────────────

def my_delay() -> None:
    time.sleep(random.choice(DELAYS))

def safe_goto(page, url: str, retries: int = 3) -> bool:
    for _ in range(retries):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(random.choice(DELAYS))
            return True
        except Exception as e:
            if 'interrupted by another navigation' in str(e):
                time.sleep(2)
                continue
            print(f'[safe_goto] {e}')
            time.sleep(2)
    return False

def check_security_verification(source: str) -> bool:
    return bool(RE_SECURITY.search(source))

def decode_html_entities(text: str) -> str:
    return (text
            .replace('&amp;', '&')
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"'))

# ─── Parsing helpers ─────────────────────────────────────────────────────────

def parse_album_page(source: str) -> dict:
    """Extract all metadata from a JavDB album page source. Returns a dict."""
    items = RE_ITEM_ORIGIN.findall(source) or RE_ITEM_CURRENT.findall(source)
    return {
        'items':      items,
        'actors':     RE_ACTORS.findall(source),
        'series':     RE_SERIES.findall(source),
        'tags':       RE_TAGS.findall(source),
        'rate':       (RE_RATES.findall(source) or ['0.0'])[0],
        'release':    (RE_RELEASES.findall(source) or [''])[0],
        'img_link':   (RE_IMG_LINKS.findall(source) or [''])[0],
    }

def parse_magnet_items(source: str) -> list[tuple]:
    """Extract magnet links and metadata from page source using BeautifulSoup."""
    from bs4 import BeautifulSoup
    results = []
    soup = BeautifulSoup(source, 'html.parser')

    for item_div in soup.find_all('div', class_='item'):
        name_span = item_div.find('span', class_='name')
        meta_span = item_div.find('span', class_='meta')
        mag_button = item_div.find('button', attrs={'data-clipboard-text': True})
        time_span = item_div.find('span', class_='time')

        if mag_button:
            name = name_span.get_text(strip=True) if name_span else ''
            meta = meta_span.get_text(strip=True) if meta_span else ''
            mag = mag_button.get('data-clipboard-text', '').strip()
            ts = time_span.get_text(strip=True) if time_span else ''

            if mag:
                results.append((mag, name, meta, ts))

    return results

def extract_id_from_filename(filename: str) -> str | None:
    filename = VIDEO_EXT_RE.sub('', filename.upper())
    filename = JUNK_RE.sub('', filename)
    for pattern in RE_ID_PATTERNS:
        m = pattern.search(filename)
        if m:
            return m.group(1).replace(' ', '-')
    return None

def convert_linux_to_windows_path(linux_path: str) -> str | None:
    if not linux_path:
        return None
    # Sort longest prefix first so longer paths match before shorter ones
    for prefix, win_prefix in sorted(PATH_MAP.items(), key=lambda x: -len(x[0])):
        if linux_path.startswith(prefix):
            remainder = linux_path[len(prefix):].lstrip('/')
            full = win_prefix.rstrip('/') + ('\\' + remainder if remainder else '')
            return full.replace('/', '\\')
    return linux_path

# ─── Domain model ────────────────────────────────────────────────────────────

class AlbumInfo:
    __slots__ = ('url', 'aid', 'release_date', 'has_magnet', 'actors',
                 'series', 'tags', 'rate', 'release', 'img_link', 'title', 'magnet_links')

    def __init__(self, url, aid, release_date, has_magnet, actors, series,
                 tags, rate, release, img_link, title=''):
        self.url          = url
        self.aid          = aid
        self.release_date = release_date
        self.has_magnet   = has_magnet
        self.actors       = actors
        self.series       = series
        self.tags         = tags
        self.rate         = rate
        self.release      = release
        self.img_link     = img_link
        self.title        = title
        self.magnet_links: list[tuple] = []

    @classmethod
    def from_parsed(cls, url: str, aid: str, data: dict, title: str) -> 'AlbumInfo':
        return cls(
            url, aid, data['release'], True,
            data['actors'], data['series'], data['tags'],
            data['rate'], data['release'], data['img_link'], title
        )

# ─── Local scan worker ───────────────────────────────────────────────────────

class LocalScanWorker:
    def __init__(self, files, page, app, browser=None, playwright=None):
        self.files      = files
        self.page       = page
        self.app        = app
        self.browser    = browser
        self.playwright = playwright
        self.albums: list[AlbumInfo] = []
        self.current_index = 0
        self._running  = False
        self.callback  = None   # set by caller

    def start(self):
        self._running = True
        self.current_index = 0

    def stop(self):
        self._running = False

    def is_running(self) -> bool:
        return self._running and self.current_index < len(self.files)

    def get_progress(self) -> tuple[int, int]:
        return self.current_index, len(self.files)

    def _advance(self, cb, log_msg: str | None = None):
        """Increment index, optionally log, and fire progress callback."""
        if log_msg:
            cb('log', log_msg)
        self.current_index += 1
        cb('progress', (self.current_index, len(self.files)))

    def process_one(self, cb) -> bool:
        if not self._running or self.current_index >= len(self.files):
            cb('finished', self.albums)
            return False

        if not (self.page and self.browser and self.playwright):
            cb('log', '[LOCAL] Browser not available, stopping scan')
            cb('finished', self.albums)
            return False

        f     = self.files[self.current_index]
        total = len(self.files)

        try:
            aid = extract_id_from_filename(f.name)
            if not aid:
                self._advance(cb, f'[LOCAL] Cannot extract ID from: {f.name}')
                return True

            cb('log', f'[LOCAL] Searching: {aid}')
            if not safe_goto(self.page, f'https://javdb.com/search?q={aid}&f=all'):
                self._advance(cb, f'[LOCAL] Failed to search: {aid}')
                return True

            source = self.page.content()
            album_links = RE_ALBUM_LINKS.findall(source)
            if not album_links:
                self._advance(cb, f'[LOCAL] No album found: {aid}')
                return True

            album_url = 'https://javdb.com' + album_links[0]
            cb('log', f'[LOCAL] Found album: {album_url}')

            if not safe_goto(self.page, album_url):
                self._advance(cb, f'[LOCAL] Failed to load album: {aid}')
                return True

            source  = self.page.content()
            parsed  = parse_album_page(source)
            items   = parsed['items']
            if not items:
                cb('log', f'[LOCAL] SKIP {aid} (cannot parse)')
                self._advance(cb)
                return True

            real_aid = items[0][0]
            title    = items[0][1] if len(items[0]) > 1 else ''
            album    = AlbumInfo.from_parsed(album_url, real_aid, parsed, title)
            self.albums.append(album)
            cb('log', f'[LOCAL] Found: {real_aid} - {title} ({len(parsed["actors"])} actors)')
            cb('album_found', album)

        except Exception as e:
            cb('log', f'[LOCAL] Error: {e}')

        self._advance(cb)
        return True

# ─── Main window ─────────────────────────────────────────────────────────────

class JdbDownloader(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('JAV DB Downloader')
        self.resize(1400, 900)

        self.playwright = None
        self.browser    = None
        self.page       = None

        # aria2
        try:
            self.aria2 = aria2p.API(aria2p.Client(host=ARIA2_SERVER, port=6800, secret=''))
        except Exception:
            self.aria2 = None
            print('aria2 not available')

        # PikPak
        self.pikpak = None
        if PIKPAK_TOKEN:
            try:
                self.pikpak = PikPakApi(encoded_token=PIKPAK_TOKEN)
                self.log('[INIT] PikPak token loaded')
            except Exception as e:
                error_msg = str(e)
                if 'token' in error_msg.lower():
                    print(f'❌ PikPak TOKEN ERROR: {error_msg}')
                    print('Please regenerate the token using get_pikpak_token.py')
                else:
                    print(f'❌ PikPak initialization error: {error_msg}')
        else:
            self.log('[INIT] PikPak token not found (pikpak_token.db)')

        # DataFrames
        self.df_maglink   = load_df(MAGLINK_FN)
        self.df_javdb     = load_df(JAVDB_FN)
        self.df_collection = load_df(COLLECTION_FN)
        self.df_check     = load_df(CHECK_FN, columns=['ID', 'check_date'])

        # Log DataFrame loading status
        print(f'[INIT] COLLECTION_FN: {COLLECTION_FN}')
        print(f'[INIT] Collection DataFrame loaded: {not self.df_collection.empty} (rows: {len(self.df_collection)})')
        if not self.df_collection.empty:
            print(f'[INIT] Collection columns: {list(self.df_collection.columns)}')

        # Fast-lookup sets (kept in sync with DataFrames)
        self.downloaded_maglinks: set[str] = (
            set(self.df_maglink['id'].tolist())
            if not self.df_maglink.empty and 'id' in self.df_maglink.columns else set()
        )
        self.id_list: set[str] = (
            set(self.df_javdb['ID'].tolist())
            if not self.df_javdb.empty and 'ID' in self.df_javdb.columns else set()
        )
        self.collection_ids: set[str] = (
            set(self.df_javdb.loc[self.df_javdb['AV'].str.contains('Collection', na=False), 'ID'].tolist())
            if not self.df_javdb.empty and 'AV' in self.df_javdb.columns else set()
        )
        self.check_list: set[str] = (
            set(self.df_collection['ID'].tolist())
            if not self.df_collection.empty and 'ID' in self.df_collection.columns else set()
        )
        self.checked_ids: set[str] = (
            set(self.df_check['ID'].tolist())
            if not self.df_check.empty and 'ID' in self.df_check.columns else set()
        )
        self.saved_ids_this_session: set[str] = set()

        # Scan state
        self.current_page        = 1
        self.current_album: AlbumInfo | None = None
        self.paused_album:  AlbumInfo | None = None
        self.is_scanning         = False
        self._is_local_scanning  = False
        self._page_unsaved_count = 0
        self.page_to             = 1
        self.base_url            = 'https://javdb.com/censored'
        self.current_page_display = ''
        self.magnet_list: list[str] = []
        self.local_files_list: list[dict] = []

        self.t_now    = pd.Timestamp.now()
        self.t_h1year = self.t_now - pd.Timedelta(270, 'D')

        self._init_ui()

    # ── Initialisation helpers ────────────────────────────────────────────────

    def _init_browser(self):
        try:
            self.playwright = sync_playwright().start()
            self.browser    = self.playwright.chromium.connect_over_cdp('http://localhost:9222')
            ctx  = self.browser.contexts[0]
            self.page = ctx.pages[0] if ctx.pages else ctx.new_page()
            self.log('Browser connected via CDP')
        except Exception as e:
            self.log(f'Browser connection failed: {e}')
            self.playwright = self.browser = None

    def _init_clipboard_timer(self):
        self.last_clip = ''
        self.clip_timer = QTimer(self)
        self.clip_timer.timeout.connect(self.check_clipboard)
        self.clip_timer.start(2000)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        # ── Top row ──────────────────────────────────────────────────────────
        top = QHBoxLayout()

        # Page range
        page_grp = QGroupBox('Page Range')
        pl = QVBoxLayout()
        self.radio_all_pages   = QRadioButton('All Pages')
        self.radio_single_page = QRadioButton('Single Page')
        self.radio_page_range  = QRadioButton('Page Range (from-to)')
        self.radio_all_pages.setChecked(True)
        rl = QHBoxLayout()
        rl.addWidget(QLabel('From:'))
        self.spin_from = QSpinBox(); self.spin_from.setValue(1); self.spin_from.setMaximum(9999)
        rl.addWidget(self.spin_from)
        rl.addWidget(QLabel('To:'))
        self.spin_to = QSpinBox(); self.spin_to.setValue(1); self.spin_to.setMaximum(9999)
        rl.addWidget(self.spin_to)
        for w in (self.radio_all_pages, self.radio_single_page, self.radio_page_range):
            pl.addWidget(w)
        pl.addLayout(rl)
        page_grp.setLayout(pl)

        # Search URL
        url_grp = QGroupBox('Search URL')
        ul = QVBoxLayout()
        tl = QHBoxLayout()
        tl.addWidget(QLabel('Type:'))
        self.combo_search_type = QComboBox()
        self.combo_search_type.addItems(['censored', 'uncensored', 'search', 'actor'])
        self.combo_search_type.currentTextChanged.connect(self.on_search_type_changed)
        tl.addWidget(self.combo_search_type)
        tl.addWidget(QLabel('Value:'))
        self.line_search = QLineEdit('https://javdb.com/censored')
        tl.addWidget(self.line_search)
        self.btn_start = QPushButton('Start Scan')
        self.btn_start.clicked.connect(self.start_scan)
        tl.addWidget(self.btn_start)
        ul.addLayout(tl)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel('Resume ID:'))
        self.line_resume_id = QLineEdit()
        self.line_resume_id.setPlaceholderText('Skip until this album ID is found (leave blank to start immediately)')
        r2.addWidget(self.line_resume_id)
        ul.addLayout(r2)
        url_grp.setLayout(ul)

        # Direct album link
        dlg = QGroupBox('Direct Album Link')
        dll = QHBoxLayout()
        self.line_album_link = QLineEdit()
        self.line_album_link.setPlaceholderText('https://javdb.com/v/xxx')
        self.btn_go_album = QPushButton('Go to Album')
        self.btn_go_album.clicked.connect(self.go_to_album)
        self.btn_clear_go_album = QPushButton('Clear & Go to Album')
        self.btn_clear_go_album.clicked.connect(self.clear_and_go_to_album)
        dll.addWidget(QLabel('Link/ID:'))
        dll.addWidget(self.line_album_link)
        dll.addWidget(self.btn_go_album)
        dll.addWidget(self.btn_clear_go_album)
        dlg.setLayout(dll)

        # Local scan
        local_grp = QGroupBox('Scan Local Files')
        locall = QHBoxLayout()
        self.line_local_path = QLineEdit()
        self.line_local_path.setPlaceholderText('Select folder with video files...')
        self.btn_browse     = QPushButton('Browse')
        self.btn_browse.clicked.connect(self.browse_local_folder)
        self.btn_scan_local = QPushButton('Scan Local Files')
        self.btn_scan_local.clicked.connect(self.scan_local_files)
        self.btn_stop_local = QPushButton('STOP')
        self.btn_stop_local.setEnabled(False)
        self.btn_stop_local.clicked.connect(self.stop_local_scan)
        self.progress_local = QProgressBar()
        self.progress_local.setVisible(False)
        for w in (QLabel('Path:'), self.line_local_path, self.btn_browse,
                  self.btn_scan_local, self.btn_stop_local):
            locall.addWidget(w)
        local_grp.setLayout(locall)

        top.addWidget(page_grp)
        top.addWidget(url_grp)
        top.addWidget(dlg)
        top.addWidget(local_grp)
        main.addLayout(top)
        main.addWidget(self.progress_local)

        # ── Filters ──────────────────────────────────────────────────────────
        fgrp = QGroupBox('Filters')
        fl = QHBoxLayout()
        self.chk_new_legends_only    = QCheckBox('-nl 新瓶舊酒/全部')
        self.chk_no_collection       = QCheckBox('-nc 單人/含合集')
        self.chk_force_download_again = QCheckBox('-fda 重下載/未下載')
        self.chk_uncensored          = QCheckBox('-uc 只停在-u/-c/-uc')
        self.chk_chinese             = QCheckBox('-4k 只停在-4k')
        self.chk_new_legends_only.setChecked(True)
        self.chk_force_download_again.setChecked(True)
        for w in (self.chk_new_legends_only, self.chk_no_collection,
                  self.chk_force_download_again, self.chk_uncensored, self.chk_chinese):
            fl.addWidget(w)
        fgrp.setLayout(fl)
        main.addWidget(fgrp)

        # ── Destination ───────────────────────────────────────────────────────
        dl = QHBoxLayout()
        dl.addWidget(QLabel('Download to:'))
        self.combo_dest = QComboBox()
        self.combo_dest.addItems(['aria2', 'pikpak'])
        dl.addWidget(self.combo_dest)
        dl.addStretch()
        main.addLayout(dl)

        # ── Control buttons ───────────────────────────────────────────────────
        cl = QHBoxLayout()
        self.btn_continue     = QPushButton('Continue to Next')
        self.btn_skip         = QPushButton('Skip This Album')
        self.btn_save_album   = QPushButton('Save to W:/')
        self.btn_stop         = QPushButton('STOP')
        self.btn_stop.setStyleSheet('background-color:#f44336;color:white;font-weight:bold;')
        self.btn_continue.clicked.connect(self.continue_scan)
        self.btn_skip.clicked.connect(self.skip_current)
        self.btn_save_album.clicked.connect(self.save_album_info)
        self.btn_stop.clicked.connect(self.stop_scan)
        for w in (self.btn_continue, self.btn_skip, self.btn_save_album, self.btn_stop):
            cl.addWidget(w)
        main.addLayout(cl)

        # ── Status bar ────────────────────────────────────────────────────────
        il = QHBoxLayout()
        self.lbl_current_page = QLabel('Current Page: -')
        f = QFont(); f.setPointSize(14); f.setBold(True)
        self.lbl_current_page.setFont(f)
        self.lbl_album  = QLabel('Album: -')
        self.lbl_status = QLabel('Ready')
        for w in (self.lbl_current_page, self.lbl_album, self.lbl_status):
            il.addWidget(w)
        main.addLayout(il)

        self.lbl_album_info = QLabel('')
        self.lbl_album_info.setStyleSheet('font-weight:bold;color:#0066cc;')
        main.addWidget(self.lbl_album_info)

        # ── Tables layout ─────────────────────────────────────────────────────
        tables_layout = QHBoxLayout()

        # ── Magnet table ──────────────────────────────────────────────────────
        self.table_album = QTableWidget()
        self.table_album.setColumnCount(6)
        self.table_album.setHorizontalHeaderLabels(['種子的title', '檔案大小', '高清', '字幕', '破解', '日期'])
        self.table_album.horizontalHeader().setStretchLastSection(False)
        for col, w in enumerate([320, 70, 45, 45, 45, 85]):
            self.table_album.setColumnWidth(col, w)
        self.table_album.cellDoubleClicked.connect(self.on_table_double_click)
        tables_layout.addWidget(self.table_album, 3)

        # ── File Explore table ────────────────────────────────────────────────
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(4)
        self.table_files.setHorizontalHeaderLabels(['Filename', 'Size', 'Del', 'Folder'])
        self.table_files.horizontalHeader().setStretchLastSection(False)
        self.table_files.setColumnWidth(0, 300)
        self.table_files.setColumnWidth(1, 80)
        self.table_files.setColumnWidth(2, 40)
        self.table_files.setColumnWidth(3, 50)
        self.table_files.cellDoubleClicked.connect(self.on_file_double_click)
        tables_layout.addWidget(self.table_files, 2)

        main.addLayout(tables_layout)

        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setMaximumHeight(200)
        main.addWidget(self.text_output)

        self.lbl_info = QLabel('Waiting...')
        main.addWidget(self.lbl_info)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, msg: str) -> None:
        """Thread-safe logging to the text_output widget."""
        if threading.current_thread() is threading.main_thread():
            self._do_log(msg)
        else:
            # Use default argument to capture the value, not the reference
            QTimer.singleShot(0, lambda m=msg: self._do_log(m))

    def _do_log(self, msg: str) -> None:
        if msg.startswith('<'):
            cursor = self.text_output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml(str(msg) + '<br>')
            self.text_output.setTextCursor(cursor)
            self.text_output.ensureCursorVisible()
        else:
            self.text_output.append(str(msg))

    # ── Scan control ─────────────────────────────────────────────────────────

    def get_page_range(self) -> tuple[int, int]:
        if self.radio_all_pages.isChecked():
            return 1, 9999
        if self.radio_single_page.isChecked():
            p = self.spin_from.value()
            return p, p
        return self.spin_from.value(), self.spin_to.value()

    def on_search_type_changed(self, text: str) -> None:
        defaults = {
            'censored':   'https://javdb.com/censored',
            'uncensored': 'https://javdb.com/uncensored',
        }
        if text in defaults:
            self.line_search.setText(defaults[text])
        else:
            self.line_search.clear()
            placeholder = {
                'search': 'Enter search keyword (e.g., abc)',
                'actor':  'Enter actor name or full link (e.g., gyRE)',
            }
            self.line_search.setPlaceholderText(placeholder.get(text, ''))
        self.line_search.setEnabled(True)

    def start_scan(self):
        if not self.browser:
            self.log('Browser not connected')
            return

        page_from, page_to = self.get_page_range()
        self.current_page = page_from
        self.page_to      = page_to

        search_type = self.combo_search_type.currentText()
        value       = self.line_search.text().strip()

        url_map = {
            'censored':   'https://javdb.com/censored',
            'uncensored': 'https://javdb.com/uncensored',
        }
        if search_type in url_map:
            self.base_url = url_map[search_type]
        elif search_type == 'search':
            self.base_url = f'https://javdb.com/search?q={value}&f=download'
        elif search_type == 'actor':
            self.base_url = value if value.startswith('http') else f'https://javdb.com/actors/{value}'
        else:
            self.base_url = value or 'https://javdb.com/censored'

        self.is_scanning = True
        self.btn_start.setEnabled(False)
        self.log(f'Starting scan: {self.base_url}, pages {self.current_page}-{self.page_to}')
        self.process_page()

    def _security_pause(self):
        self.is_scanning = False
        self.btn_start.setEnabled(True)
        self.lbl_status.setText('SECURITY VERIFICATION REQUIRED!')
        self.log('[PAUSE] ===== SECURITY VERIFICATION DETECTED =====')
        self.log('[PAUSE] Please complete the verification in browser, then press Continue')

    def _finish_scan(self):
        self.log('=== Scan Completed ===')
        self.save_javdb_to_file()
        save_df(self.df_check, CHECK_FN)
        self.btn_start.setEnabled(True)
        self.is_scanning = False

    def process_page(self):
        if not self.is_scanning:
            return
        if self.current_page > self.page_to:
            self._finish_scan()
            return

        self.lbl_current_page.setText(f'Current Page: {self.current_page}')
        self.current_page_display = f'Page {self.current_page}'
        page_url = f'{self.base_url}?page={self.current_page}'

        try:
            if not safe_goto(self.page, page_url):
                self.log('Error loading page: retry failed')
                self.current_page += 1
                QTimer.singleShot(1000, self.process_page)
                return
            source = self.page.content()
        except Exception as e:
            self.log(f'Error loading page: {e}')
            self.current_page += 1
            QTimer.singleShot(1000, self.process_page)
            return

        if check_security_verification(source):
            self._security_pause()
            return

        links = RE_PAGE_LINKS.findall(source)
        self.log(f'Page {self.current_page}: Found {len(links)} albums')

        if not links:
            self.log('No more albums, stopping')
            self._finish_scan()
            return

        self.albums_on_page = list(links)
        self.album_index    = 0
        self.current_page  += 1
        QTimer.singleShot(500, self.process_album)

    def process_album(self):
        if not self.is_scanning:
            return
        if self.album_index >= len(self.albums_on_page):
            QTimer.singleShot(500, self.process_page)
            return

        al, aid, release_dates, dl_link = self.albums_on_page[self.album_index]
        self.album_index += 1

        m_link = 'https://javdb.com' + al
        self.lbl_album.setText(f'Album: {aid}')
        self.lbl_status.setText(f'Checking {aid}...')

        # Resume ID — skip until this ID is found
        resume_id = self.line_resume_id.text().strip().upper()
        if resume_id and aid.upper() != resume_id:
            self.log(f'[SKIP] {aid} (waiting for resume ID: {resume_id})')
            QTimer.singleShot(50, self.process_album)
            return
        if resume_id and aid.upper() == resume_id:
            self.line_resume_id.clear()
            self.log(f'[RESUME] Found resume ID {aid} — starting processing')

        # Filters
        if not self.chk_force_download_again.isChecked() and aid.upper() in self.check_list:
            self.log(f'[SKIP] {aid} already in collection')
            QTimer.singleShot(300, self.process_album)
            return

        if self.chk_new_legends_only.isChecked():
            try:
                if pd.Timestamp(release_dates) > self.t_h1year:
                    self.log(f'[SKIP] {aid} is new film ({release_dates})')
                    QTimer.singleShot(300, self.process_album)
                    return
            except Exception:
                pass

        if 'tag is-warning' not in dl_link and 'tag is-success' not in dl_link:
            self.log(f'[SKIP] {aid} has no magnet link')
            QTimer.singleShot(300, self.process_album)
            return

        self.current_album = AlbumInfo(m_link, aid, release_dates, True, [], [], [], '', '', '')

        try:
            if not safe_goto(self.page, m_link):
                self.log(f'Error loading album: retry failed')
                QTimer.singleShot(300, self.process_album)
                return
            source = self.page.content()
        except Exception as e:
            self.log(f'Error loading album: {e}')
            QTimer.singleShot(300, self.process_album)
            return

        if check_security_verification(source):
            self._security_pause()
            return

        parsed = parse_album_page(source)
        items  = parsed['items']
        title  = items[0][1] if items and len(items[0]) > 1 else ''

        self.current_album.actors  = parsed['actors']
        self.current_album.series  = parsed['series']
        self.current_album.tags    = parsed['tags']
        self.current_album.rate    = parsed['rate']
        self.current_album.release = parsed['release']
        self.current_album.img_link = parsed['img_link']
        self.current_album.title   = title

        # Solo/collection filter
        if self.chk_no_collection.isChecked() and len(parsed['actors']) != 1:
            self.log(f'[SKIP] {aid} has {len(parsed["actors"])} actors (-nc checked)')
            QTimer.singleShot(300, self.process_album)
            return

        mag_links_raw = parse_magnet_items(source)
        self.current_album.magnet_links = mag_links_raw

        if not mag_links_raw:
            self.log(f'[SKIP] {aid}: No magnets found')
            QTimer.singleShot(300, self.process_album)
            return

        # Uncensored / 4K filters
        uc = self.chk_uncensored.isChecked()
        fk = self.chk_chinese.isChecked()
        if uc or fk:
            has_uc = any('-u' in m[1].lower() or '-c' in m[1].lower() or '-uc' in m[1].lower()
                         for m in mag_links_raw)
            has_4k = any('-4k' in m[1].lower() for m in mag_links_raw)
            skip = (uc and fk and not (has_uc or has_4k)) or \
                   (uc and not fk and not has_uc) or \
                   (fk and not uc and not has_4k)
            if skip:
                self.log(f'[SKIP] {aid}: magnet filter mismatch')
                QTimer.singleShot(300, self.process_album)
                return

        if self.is_recently_checked(aid):
            self.lbl_status.setStyleSheet('color:#cc0000;font-weight:bold;')
            self.lbl_status.setText(f'⚠ {aid} was checked recently (within 10 days)')
            self.log(f'[WARNING] {aid} was checked recently (within 10 days)')

        self.display_album_info()

        if aid.upper() not in self.id_list:
            self.add_album_to_memory(self.current_album)
            self.log(f'[ADDED] {aid} to memory (scan pause)')

        self.check_collection_and_open_browser(aid)
        self.log(f'[PAUSE] {aid} - {self.current_page_display} - magnets found, waiting for decision')
        self.pause_current()

    # ── Album display ─────────────────────────────────────────────────────────

    def display_album_info(self):
        self.magnet_list = []

        def parse_size_mb(s: str) -> float:
            if not s:
                return 0.0
            s = s.upper().strip()
            num = float(re.sub(r'[^\d.]', '', s) or 0)
            return num * 1024 if 'G' in s else num

        mag_data = []
        for item in self.current_album.magnet_links:
            if len(item) < 3:
                continue
            mag, title, meta = item[0], item[1], item[2]
            date = item[3] if len(item) >= 4 else ''
            size = meta.split(',')[0].strip() if meta else ''
            tl = title.lower()
            mag_data.append({
                'mag':      mag,
                'date':     date,
                'title':    title,
                'size':     size,
                'hd':       '高清' if 'hd' in tl else '',
                'subtitle': '字幕' if '-c' in tl or '字幕' in title else '',
                'cracked':  '破解' if '-u' in tl or '無碼' in title or 'uncensored' in tl else '',
            })

        mag_data.sort(key=lambda x: (
            -(x['cracked'] == '破解'),
            -(x['subtitle'] == '字幕'),
            -(x['hd'] == '高清'),
            -parse_size_mb(x['size']),
            x['date'],
        ))

        self.table_album.setUpdatesEnabled(False)
        self.table_album.setRowCount(len(mag_data))
        for row, md in enumerate(mag_data):
            for col, val in enumerate([md['title'][:50], md['size'], md['hd'], md['subtitle'], md['cracked'], md['date']]):
                self.table_album.setItem(row, col, QTableWidgetItem(val))
            self.magnet_list.append(md['mag'])
        self.table_album.setUpdatesEnabled(True)

        actors_str = ''
        if self.current_album.actors:
            actors_str = (f'Collection ({len(self.current_album.actors)}人)'
                          if len(self.current_album.actors) > 1
                          else self.current_album.actors[0][1])

        self.lbl_album_info.setText(
            f"Actors: {actors_str} | Title: {self.current_album.title[:30]} | Release: {self.current_album.release_date}"
        )
        info = f"ID: {self.current_album.aid} | Rate: {self.current_album.rate}"
        if self.current_album.series:
            info += f" | Series: {self.current_album.series[0]}"
        self.lbl_info.setText(f'{self.current_page_display} | {info}')
        self.log(f'[TABLE] {len(mag_data)} magnets for {self.current_album.aid}')

    def on_table_double_click(self, row: int, col: int):
        if row >= len(self.magnet_list):
            return
        album = self.current_album
        if not album:
            return

        aid_upper = album.aid.upper()
        if aid_upper not in self.saved_ids_this_session:
            self.add_album_to_memory(album)
            self.save_javdb_to_file()
            # self.saved_ids_this_session is updated inside add_album_to_memory
            self.log(f'[PAGE] {album.aid} updated/saved to my javdb.json')
        
        mag = self.magnet_list[row]
        dest = self.combo_dest.currentText()
        if dest == 'aria2':
            if self.aria2:
                try:
                    download = self.aria2.add_magnet(mag, options=self.aria2.get_global_options())
                    self.log(f'[DL] Added to aria2: {download.gid}')
                except Exception as e:
                    self.log(f'[DL] aria2 error: {e}')
            else:
                self.log('[DL] aria2 not connected')
        elif dest == 'pikpak':
            if not self.pikpak:
                self.log('[DL] PikPak token not configured')
                return
            self.log(f'[DL] Sending to PikPak...')
            self._pikpak_download(mag)

    def display_local_files(self, aid: str):
        self.table_files.setRowCount(0)
        self.local_files_list = []

        self.log(f"[FILES] Loading files for {aid}...")

        if self.df_collection.empty:
            self.table_files.setRowCount(0)
            self.log("[FILES] my collection.json is empty or not found - no local files to display")
            self.log("[FILES] Tip: Create/populate my collection.json with album IDs and their local paths")
            return

        # Check required columns
        if 'ID' not in self.df_collection.columns or 'path' not in self.df_collection.columns:
            self.log(f"[FILES] ERROR: my collection.json missing required columns (ID, path)")
            self.log(f"[FILES] Available columns: {list(self.df_collection.columns)}")
            return

        # Normalize ID for matching
        aid_norm = aid.upper().strip().replace(' ', '-').replace('_', '-')
        self.log(f"[FILES] Looking for album: {aid} (normalized: {aid_norm})")

        mask = (self.df_collection['ID'].str.upper()
                .str.strip()
                .str.replace(' ', '-')
                .str.replace('_', '-') == aid_norm)
        rows = self.df_collection[mask]

        if rows.empty:
            self.log(f"[FILES] Album {aid_norm} not found in my collection.json")
            self.log(f"[FILES] Total albums in collection: {len(self.df_collection)}")
            return

        self.log(f"[FILES] Found {len(rows)} matching row(s) for {aid_norm}")

        # Try to find the first path that actually exists
        valid_path = None
        for idx, l_path in enumerate(rows['path'].values):
            w_path = convert_linux_to_windows_path(l_path)
            self.log(f"[FILES]   Path {idx+1}: Linux={l_path} -> Windows={w_path}")
            if w_path:
                if os.path.exists(w_path):
                    valid_path = w_path
                    self.log(f"[FILES]   ✓ Path exists: {w_path}")
                    break
                else:
                    self.log(f"[FILES]   ✗ Path not found: {w_path}")

        if not valid_path:
            self.log(f"[FILES] No valid local directory found for {aid_norm}")
            return

        # Scan files directly (synchronously) - no need for threading since it's fast
        self.log(f"[FILES] Scanning directory: {valid_path[:60]}...")
        try:
            files_data = []
            items = os.listdir(valid_path)
            self.log(f"[FILES] Found {len(items)} items in directory")

            for item_name in items:
                try:
                    item_path = os.path.join(valid_path, item_name)

                    # Check if it's a file
                    if not os.path.isfile(item_path):
                        continue

                    # Check if it's a video file
                    name_lower = item_name.lower()
                    if any(name_lower.endswith(ext) for ext in VIDEO_EXTS):
                        try:
                            size = os.path.getsize(item_path)
                            files_data.append({'name': item_name, 'size': size, 'path': item_path})
                            self.log(f"[FILES]   ✓ {item_name[:45]} ({size / (1024*1024*1024):.2f} GB)")
                        except Exception as e:
                            self.log(f"[FILES]   ⚠ Can't read size: {e}")
                            files_data.append({'name': item_name, 'size': 0, 'path': item_path})
                except Exception as item_err:
                    self.log(f"[FILES]   ⚠ Error: {item_err}")
                    continue

            files_data.sort(key=lambda x: x['size'], reverse=True)
            self.log(f"[FILES] ✓ Scan complete: {len(files_data)} video file(s) found")

            # Update UI directly (synchronously)
            self._update_files_table(files_data, aid)

        except Exception as e:
            self.log(f"[FILES] ❌ Error scanning directory: {type(e).__name__}: {e}")
            self._update_files_table([], aid)

    def _update_files_table(self, files_data, aid):
        try:
            self.log(f"[FILES] _update_files_table called for {aid} with {len(files_data)} files")

            # Always clear the table first
            self.table_files.setRowCount(0)
            self.local_files_list = []

            if not files_data:
                self.log(f'[FILES] No video files found in the album folder for {aid}')
                # Show "No files" message in table
                self.table_files.insertRow(0)
                no_files_item = QTableWidgetItem(f'No video files found for {aid}')
                self.table_files.setItem(0, 0, no_files_item)
                return

            self.log(f"[FILES] Adding {len(files_data)} rows to table")

            for idx, fd in enumerate(files_data):
                try:
                    row_idx = self.table_files.rowCount()
                    self.table_files.insertRow(row_idx)
                    self.log(f"[FILES]   Row {row_idx}: {fd.get('name', 'unknown')[:30]}")

                    # Filename
                    name_item = QTableWidgetItem(str(fd['name']))
                    self.table_files.setItem(row_idx, 0, name_item)

                    # Size
                    size_gb = fd['size'] / (1024*1024*1024)
                    size_str = f"{size_gb:.2f} GB" if size_gb >= 1 else f"{fd['size'] / (1024*1024):.2f} MB"
                    self.table_files.setItem(row_idx, 1, QTableWidgetItem(size_str))

                    # Delete icon
                    del_item = QTableWidgetItem('🗑')
                    self.table_files.setItem(row_idx, 2, del_item)

                    # Folder icon
                    folder_item = QTableWidgetItem('📁')
                    self.table_files.setItem(row_idx, 3, folder_item)

                    self.local_files_list.append(fd)
                except Exception as row_err:
                    self.log(f"[FILES] Error adding row {idx}: {row_err}")
                    continue

            self.log(f'[FILES] ✓ Successfully displayed {len(self.local_files_list)} file(s) in table')
        except Exception as e:
            self.log(f"[FILES] ERROR updating UI table for {aid}: {type(e).__name__}: {e}")
            import traceback
            self.log(f"[FILES] Traceback: {traceback.format_exc()}")
            # Show error in table
            self.table_files.setRowCount(0)
            self.table_files.insertRow(0)
            error_item = QTableWidgetItem(f'Error loading files: {str(e)[:40]}')
            self.table_files.setItem(0, 0, error_item)

    def on_file_double_click(self, row, col):
        if row >= len(self.local_files_list):
            return

        file_info = self.local_files_list[row]
        if col == 2: # Delete column
            self.delete_file(row)
        elif col == 3: # Folder column
            self.open_file_folder(file_info['path'])
        else:
            # Play with VLC
            vlc_paths = [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            ]
            vlc_exe = None
            for p in vlc_paths:
                if os.path.exists(p):
                    vlc_exe = p
                    break

            try:
                if vlc_exe:
                    # Use absolute path and ensure it's quoted if needed by Popen
                    subprocess.Popen([vlc_exe, file_info['path']])
                    self.log(f'[VLC] Playing: {file_info["name"]}')
                else:
                    # Fallback to system default player
                    os.startfile(file_info['path'])
                    self.log(f'[OPEN] Playing with default player: {file_info["name"]}')
            except Exception as e:
                self.log(f'[PLAY] Error: {e}')

    def delete_file(self, row):
        file_info = self.local_files_list[row]
        try:
            os.remove(file_info['path'])
            self.log(f'[DELETE] File deleted: {file_info["name"]}')
            self.table_files.removeRow(row)
            self.local_files_list.pop(row)
        except Exception as e:
            self.log(f'[DELETE] Error: {e}')

    def open_file_folder(self, file_path):
        try:
            folder_path = os.path.dirname(file_path)
            subprocess.Popen(['explorer.exe', '/select,', file_path])
            self.log(f'[FOLDER] Opened folder: {folder_path}')
        except Exception as e:
            self.log(f'[FOLDER] Error opening folder: {e}')

    # ── Scan state management ─────────────────────────────────────────────────

    def pause_current(self):
        self.paused_album = self.current_album
        self.log(f'Paused: {self.current_album.aid}')
        self.display_local_files(self.current_album.aid)

    def continue_scan(self):
        if self.paused_album:
            self.save_to_check_json(self.paused_album.aid)
            self.add_album_to_memory(self.paused_album)
        self.log(f'[CONTINUE] {self.paused_album.aid if self.paused_album else ""} - proceeding')
        QTimer.singleShot(300, self.process_album)

    def skip_current(self):
        self.log(f'[SKIP BTN] {self.paused_album.aid if self.paused_album else ""} - manually skipped')
        QTimer.singleShot(300, self.process_album)

    def stop_scan(self):
        self.is_scanning = False
        self.btn_start.setEnabled(True)
        self.lbl_status.setStyleSheet('')
        self.lbl_status.setText('STOPPED - Ready for new scan')
        self.lbl_current_page.setText('Current Page: -')
        self.save_javdb_to_file()
        save_df(self.df_check, CHECK_FN)
        self.log('[STOP] Scan stopped by user.')

    # ── Check / recently-checked logic ────────────────────────────────────────

    def is_recently_checked(self, aid: str) -> bool:
        if self.df_check.empty or 'ID' not in self.df_check.columns:
            return False
        aid_norm = aid.upper().strip().replace(' ', '-').replace('_', '-')
        mask = (self.df_check['ID'].str.upper()
                .str.strip()
                .str.replace(' ', '-')
                .str.replace('_', '-') == aid_norm)
        rows = self.df_check[mask]
        if rows.empty:
            return False
        try:
            days = (pd.Timestamp.now() - pd.to_datetime(rows['check_date'].iloc[0])).days
            return days <= 10
        except Exception:
            return False

    def save_to_check_json(self, aid: str):
        aid_upper = aid.upper()
        if self.df_check.empty:
            self.df_check = pd.DataFrame(columns=['ID', 'check_date'])
        self.df_check = self.df_check[self.df_check['ID'].str.upper() != aid_upper]
        new_row = pd.DataFrame([{'ID': aid_upper, 'check_date': pd.Timestamp.now().strftime('%Y-%m-%d')}])
        self.df_check = pd.concat([self.df_check, new_row], ignore_index=True)
        save_df(self.df_check, CHECK_FN)

    # ── Direct album navigation ───────────────────────────────────────────────

    def go_to_album(self):
        if not self.browser:
            self.log('Browser not connected')
            return
        
        # Ensure we have the latest page reference
        try:
            ctx = self.browser.contexts[0] if self.browser and self.browser.contexts else None
            if ctx and ctx.pages:
                self.page = ctx.pages[0]
        except Exception:
            pass

        link = self.line_album_link.text().strip()

        if link:
            if link.startswith('http'):
                self.log(f'Loading album: {link}')
                if not safe_goto(self.page, link):
                    self.log('Failed to load album')
                    return
            else:
                # Search for ID
                search_url = f"https://javdb.com/search?q={link}&f=all"
                self.log(f'Searching for ID {link}')
                if not safe_goto(self.page, search_url):
                    self.log('Failed to reach search page')
                    return

                try:
                    self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                    first_album = self.page.query_selector('.movie-list .item a, .video-list .item a, a[href^="/v/"]')
                    if first_album:
                        href = first_album.get_attribute('href')
                        if not href.startswith('http'):
                            href = 'https://javdb.com' + href
                        self.log(f'Found search result, loading album...')
                        if not safe_goto(self.page, href):
                            self.log('Failed to navigate to search result')
                            return
                    else:
                        self.log(f'No search results found for ID: {link}')
                        return
                except Exception as e:
                    self.log(f'Error during search: {e}')
                    return
        else:
            # If no link provided, check if current page is already an album
            try:
                cur_url = str(self.page.url)
                if '/v/' not in cur_url:
                    self.log('No album link provided, finding first album...')
                    self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                    links = self.page.query_selector_all('a[href*="/v/"]')
                    if links:
                        href = links[0].get_attribute('href')
                        if not href.startswith('http'):
                            href = 'https://javdb.com' + href
                        self.log(f'Loading album...')
                        if not safe_goto(self.page, href):
                            self.log('Failed to navigate to album')
                            return
                    else:
                        self.log('No album link found')
                        return
            except Exception as e:
                self.log(f'Error identifying album page: {e}')
                return

        source = ''
        for attempt in range(3):
            try:
                # Refresh page object in each attempt to avoid stale references
                ctx = self.browser.contexts[0] if self.browser and self.browser.contexts else None
                if ctx and ctx.pages:
                    self.page = ctx.pages[0]

                self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                cur_url = str(self.page.url)
                if '/v/' not in cur_url:
                    if attempt < 2:
                        time.sleep(0.2)
                        continue
                    self.log(f'Current page is not an album page: {cur_url}')
                    return

                source = self.page.content()
                if source and len(source) > 100 and 'magnet:' in source:
                    break
                elif attempt < 2:
                    time.sleep(0.3)
                    continue
            except Exception as e:
                if 'context was destroyed' in str(e) or 'navigation' in str(e):
                    if attempt < 2:
                        time.sleep(0.2)
                        continue
                self.log(f'Attempt {attempt+1} failed: {e}')
                if attempt == 2:
                    return
                time.sleep(0.2)

        if not source or len(source) < 100:
            self.log('Failed to retrieve page content')
            return

        if check_security_verification(source):
            self.log('[PAUSE] ===== SECURITY VERIFICATION DETECTED =====')
            self.lbl_status.setText('SECURITY VERIFICATION REQUIRED!')
            return

        parsed = parse_album_page(source)
        items  = parsed['items']
        if not items:
            self.log('Cannot find album ID')
            return

        aid   = items[0][0]
        title = items[0][1] if len(items[0]) > 1 else ''
        page_url = str(self.page.url)
        self.log(f'Album: {aid} - {title}')

        album = AlbumInfo.from_parsed(page_url, aid, parsed, title)
        album.magnet_links = parse_magnet_items(source)
        self.current_album = album
        self.paused_album = album

        self.add_album_to_memory(album)
        self.save_javdb_to_file()
        self.log(f'[ADDED] {aid} to my javdb.json')

        if self.is_recently_checked(aid):
            self.log(f'<span style="color:red;font-weight:bold;">[WARN] {aid} 在近幾天已check過</span>')

        self.check_collection_and_open_browser(aid)
        self.display_album_info()
        self.lbl_status.setText(f'Album: {aid}')
        self.display_local_files(aid)

    def clear_and_go_to_album(self):
        self.line_album_link.clear()
        self.go_to_album()

    # ── Collection helper ─────────────────────────────────────────────────────

    def check_collection_and_open_browser(self, aid: str):
        if self.df_collection.empty or 'ID' not in self.df_collection.columns:
            return
        aid_norm = aid.upper().strip().replace(' ', '-').replace('_', '-')
        mask = (self.df_collection['ID'].str.upper()
                .str.strip()
                .str.replace(' ', '-')
                .str.replace('_', '-') == aid_norm)
        row = self.df_collection[mask]
        if not row.empty:
            self.log(f'[COLLECTION] {aid} already in collection — skip opening browser')
            return

    # ── Clipboard handling ────────────────────────────────────────────────────

    def check_clipboard(self):
        if not self.is_scanning:
            return
        try:
            cur = pyperclip.paste()
        except Exception:
            return
        if not cur or cur == self.last_clip:
            return
        self.last_clip = cur

        mag_links   = RE_MAGNET.findall(cur)
        album_links = RE_JAVDB_ALBUM.findall(cur)

        if mag_links:
            self.handle_magnet_from_clipboard(mag_links)
        elif album_links:
            self.handle_album_from_clipboard(album_links)

    def handle_magnet_from_clipboard(self, mag_links: list[str]):
        dest = self.combo_dest.currentText()
        for mag in mag_links:
            mag_clean = decode_html_entities(mag)
            self.log(f'[Clipboard] Magnet detected: {mag_clean[:40]}...')

            if self.current_album and self.current_album.aid:
                if self.current_album.aid.upper() not in self.id_list:
                    self.add_album_to_memory(self.current_album)
                    self.log(f'[Clipboard] Album {self.current_album.aid} added to memory')

            if dest == 'pikpak':
                if not self.pikpak:
                    self.log('[Clipboard] PikPak token not configured')
                else:
                    self.log('[Clipboard] Sending to PikPak...')
                    self._pikpak_download(mag_clean)
            elif dest == 'aria2':
                if self.aria2:
                    try:
                        download = self.aria2.add_magnet(mag_clean, options=self.aria2.get_global_options())
                        self.log(f'[Clipboard] Added to aria2: {download.gid}')
                    except Exception as e:
                        self.log(f'[Clipboard] aria2 error: {e}')
                else:
                    self.log('[Clipboard] aria2 not connected — skipping')

            self._append_maglink(mag_clean)

    def handle_album_from_clipboard(self, album_links: list[str]):
        for link in album_links:
            self.log(f'[Clipboard] Album link: {link}')

    def check_clipboard_and_download(self):
        try:
            cur = pyperclip.paste()
        except Exception:
            return
        mag_links = RE_MAGNET.findall(cur)
        if not mag_links:
            return

        dest = self.combo_dest.currentText()
        self.log(f'[CLIPBOARD] Found {len(mag_links)} magnet(s) — dest: {dest}')
        for mag in mag_links:
            mag_clean = decode_html_entities(mag)
            self.log(f'[CLIPBOARD] Magnet: {mag_clean[:50]}...')
            if dest == 'pikpak':
                if self.pikpak:
                    self.log('[CLIPBOARD] Sending to PikPak...')
                    self._pikpak_download(mag_clean)
                else:
                    self.log('[CLIPBOARD] PikPak token not configured — skipping')
                    continue
            elif dest == 'aria2':
                if self.aria2:
                    try:
                        dl = self.aria2.add_magnet(mag_clean)
                        self.log(f'[CLIPBOARD] Added to aria2: {dl.gid}')
                    except Exception as e:
                        self.log(f'[CLIPBOARD] aria2 error: {e}')
                else:
                    self.log('[CLIPBOARD] aria2 not connected — skipping')
            self._append_maglink(mag_clean)
        self.log('[CLIPBOARD] Magnet(s) processed')
        pyperclip.copy('')

    def _append_maglink(self, mag_clean: str):
        """Append a magnet link to the in-memory df and persist."""
        new_row = pd.DataFrame([{
            'id':      mag_clean,
            'cast':    '',
            'date':    datetime.now().strftime('%Y-%m-%d'),
            'title':   '',
            'maglink': mag_clean,
        }])
        self.df_maglink = pd.concat([self.df_maglink, new_row], ignore_index=True)
        self.downloaded_maglinks.add(mag_clean)
        save_df(self.df_maglink, MAGLINK_FN)
        self.log('[Clipboard] Magnet saved')

    def _pikpak_download(self, link: str):
        """Send magnet or URL to PikPak for download."""
        import threading
        def _thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._pikpak_async(link))
            except Exception as e:
                self.log(f'[DL] PikPak thread error: {str(e)[:300]}')
            finally:
                loop.close()
        threading.Thread(target=_thread, daemon=True).start()

    async def _pikpak_async(self, link: str):
        """Async PikPak download handler."""
        try:
            self.log(f'[DL] Refreshing PikPak token...')
            await self.pikpak.refresh_access_token()
            self.save_pikpak_token()
            self.log(f'[DL] Token refreshed and saved, sending to PikPak...')

            result = await self.pikpak.offline_download(file_url=link)

            self.log(f'[DL] PikPak response received')
            task = result.get('task', {})
            tid = task.get('id', 'unknown')
            self.log(f'[DL] PikPak task added: {tid}')
        except Exception as e:
            import traceback
            error_msg = str(e)

            # Check for token-related errors
            if 'token' in error_msg.lower() or 'unauthorized' in error_msg.lower() or 'auth' in error_msg.lower():
                self.log(f'[DL] ❌ PikPak TOKEN ERROR: {error_msg[:200]}')
                self.log(f'[DL] Please check: pikpak_token.db file or regenerate the token')
            elif '401' in error_msg or '403' in error_msg:
                self.log(f'[DL] ❌ PikPak AUTHENTICATION FAILED: {error_msg[:200]}')
                self.log(f'[DL] Token may have expired. Please regenerate it.')
            else:
                self.log(f'[DL] ❌ PikPak error: {error_msg[:300]}')

            tb = traceback.format_exc()[:500]
            if tb and 'token' in tb.lower():
                self.log(f'[DL] Token-related traceback: {tb}')

    # ── Download ──────────────────────────────────────────────────────────────

    def download_magnet(self):
        if not self.paused_album:
            return
        dest = self.combo_dest.currentText()
        for item in self.paused_album.magnet_links:
            mag_clean = decode_html_entities(item[0])
            if dest == 'pikpak':
                self.log(f'[DL] PikPak mode — skipping aria2 for {mag_clean[:40]}...')
                self._append_maglink(mag_clean)
                continue
            if not self.aria2:
                self.log('[DL] aria2 not connected')
                continue
            try:
                avid_i   = str(random.random())
                dl_path  = Path('/volume1/aria2/_dl') / avid_i
                ks       = self.aria2.get_global_options()
                ks.dir   = str(dl_path).replace('\\', '/')
                download = self.aria2.add_magnet(mag_clean, options=ks)
                self.log(f'Added to aria2: {download.gid}')
                self._append_maglink(mag_clean)
            except Exception as e:
                self.log(f'aria2 error: {e}')
        self.log('Magnet(s) saved to maglink_added.json')

    # ── Memory / persistence ──────────────────────────────────────────────────

    def save_pikpak_token(self):
        """Save the current PikPak token state to pikpak_token.db."""
        if not self.pikpak:
            return
        try:
            # Re-read existing file to preserve other fields if any
            token_data = {}
            if TOKEN_FILE.exists():
                try:
                    with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                        token_data = json.load(f)
                except Exception:
                    pass
            
            token_data['encoded_token'] = self.pikpak.encoded_token
            token_data['access_token']  = self.pikpak.access_token
            token_data['refresh_token'] = self.pikpak.refresh_token
            
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, indent=4)
            # self.log('[SAVE] PikPak token updated in pikpak_token.db') # Too noisy if logged on every download
        except Exception as e:
            self.log(f'[ERROR] Failed to save PikPak token: {e}')

    def add_album_to_memory(self, album: AlbumInfo):
        if not album:
            return
        aid    = album.aid.strip().upper().replace(' ', '-')
        actors = album.actors  # list of (alink_str, name_str) tuples

        # Remove any existing entry with the same album ID
        if not self.df_javdb.empty and 'ID' in self.df_javdb.columns:
            mask = ~self.df_javdb['ID'].str.upper().str.strip().str.replace(' ', '-').str.replace('_', '-').eq(aid)
            self.df_javdb = self.df_javdb[mask]

        def make_row(av: str, cast: str) -> dict:
            return {
                'AV':             av,
                'Album':          album.title.strip() if album.title else '',
                'count':          0,
                'size':           0,
                'path':           0,
                'ID':             aid.upper().strip(),
                'Cast':           cast,
                'album_img_link': album.img_link.strip() if album.img_link else '',
                'rate':           album.rate.strip()     if album.rate     else '',
                'series':         [s.strip() for s in album.series] if album.series else [],
                'tags':           [t.strip() for t in album.tags]   if album.tags   else [],
                'actors':         actors,
                'release':        album.release.strip()  if album.release  else '',
            }

        UNKNOWN = '見つかりませ女優の情報なし'
        if not actors:
            # No actress tag on page — save with placeholder, actors list carries the sentinel
            placeholder_actors = [('', UNKNOWN)]
            row = make_row(UNKNOWN, UNKNOWN)
            row['actors'] = placeholder_actors
            self.df_javdb = pd.concat(
                [self.df_javdb, pd.DataFrame([row])],
                ignore_index=True
            )
        elif len(actors) > 1:
            # Collection — one row, AV = 'Collection', Cast = all names joined
            all_names = ', '.join(name.strip() for _, name in actors if name)
            self.df_javdb = pd.concat(
                [self.df_javdb, pd.DataFrame([make_row('Collection', all_names)])],
                ignore_index=True
            )
        else:
            # Solo — one row per actress (usually just one)
            for _alink, name in actors:
                name = name.strip() if name else ''
                self.df_javdb = pd.concat(
                    [self.df_javdb, pd.DataFrame([make_row(name, name)])],
                    ignore_index=True
                )

        # keep id_list set in sync with cleaned aid
        cleaned_aid = aid.strip().upper()
        self.id_list.discard(cleaned_aid)
        self.id_list.add(cleaned_aid)
        self.saved_ids_this_session.add(cleaned_aid)
        self.log(f'[ADDED] {aid} | title: {album.title[:30] if album.title else "(empty)"} to memory')

    def save_javdb_to_file(self):
        save_df(self.df_javdb, JAVDB_FN)
        self.log('[SAVED] my javdb.json saved to disk')

    def save_album_info(self):
        self.save_javdb_to_file()
        src = JAVDB_FN
        dst = Path('w:/my javdb.json')
        if not src.exists():
            self.log('[ERROR] my javdb.json not found')
            return
        try:
            shutil.copy2(src, dst)
            self.log(f'[COPIED] my javdb.json -> w:/my javdb.json')
        except Exception as e:
            self.log(f'[ERROR] Failed to copy: {e}')

    # ── Local file scan ───────────────────────────────────────────────────────

    def browse_local_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder with Videos')
        if folder:
            self.line_local_path.setText(folder)

    def scan_local_files(self):
        if not self.browser:
            self.log('Browser not connected')
            return
        self.table_album.setRowCount(0)
        folder = self.line_local_path.text().strip()
        if not folder or not Path(folder).exists():
            self.log('Please select a valid folder')
            return

        files = [f for f in Path(folder).rglob('*') if f.is_file() and f.suffix.lower() in VIDEO_EXTS]
        if not files:
            self.log('No video files found')
            return

        self.log(f'[LOCAL] Found {len(files)} video files')
        self.btn_scan_local.setEnabled(False)
        self.btn_stop_local.setEnabled(True)
        self.progress_local.setVisible(True)
        self.progress_local.setMaximum(len(files))
        self.progress_local.setValue(0)

        SAVE_EVERY = 4   # flush to disk after every N albums added

        def worker_callback(event, data):
            try:
                if event == 'log':
                    self.log(data)
                elif event == 'album_found':
                    album = data
                    self.add_album_to_memory(album)
                    self._local_unsaved_count += 1
                    if self._local_unsaved_count >= SAVE_EVERY:
                        self.save_javdb_to_file()
                        self._local_unsaved_count = 0
                    self.progress_local.setValue(self.local_worker.current_index)
                    QApplication.instance().processEvents()
                    QTimer.singleShot(5, self._local_scan_next)
                elif event == 'progress':
                    current, _ = data
                    self.progress_local.setValue(current)
                    QApplication.instance().processEvents()
                elif event == 'finished':
                    self._is_local_scanning = False
                    self.on_local_finished(data)
            except Exception as e:
                print(f'[LOCAL] Callback error: {e}')
                self._is_local_scanning = False

        self._local_unsaved_count = 0

        self.local_worker = LocalScanWorker(files, self.page, QApplication.instance(), self.browser, self.playwright)
        self.local_worker.callback = worker_callback
        self._is_local_scanning = True
        self.local_worker.start()
        self._local_scan_next()

    def _local_scan_next(self):
        try:
            if not self._is_local_scanning:
                return
            if not getattr(self, 'local_worker', None):
                return
            if not self.local_worker.is_running():
                self._is_local_scanning = False
                self.on_local_finished(self.local_worker.albums)
                return
            more = self.local_worker.process_one(self.local_worker.callback)
            if not more:
                self._is_local_scanning = False
                self.on_local_finished(self.local_worker.albums)
        except Exception as e:
            self.log(f'[LOCAL] _local_scan_next error: {e}')
            self._is_local_scanning = False
            self.btn_scan_local.setEnabled(True)
            self.btn_stop_local.setEnabled(False)
            self.progress_local.setVisible(False)

    def stop_local_scan(self):
        worker = getattr(self, 'local_worker', None)
        if worker and worker._running:
            worker.stop()
            self.log('[LOCAL] Scan stopped by user')
        self.btn_scan_local.setEnabled(True)
        self.btn_stop_local.setEnabled(False)
        self.progress_local.setVisible(False)
        self._is_local_scanning = False

    def on_local_finished(self, albums: list[AlbumInfo]):
        self.btn_scan_local.setEnabled(True)
        self.btn_stop_local.setEnabled(False)
        self.progress_local.setVisible(False)
        self._is_local_scanning = False
        if not albums:
            self.log('[LOCAL] No albums found')
            return
        # Albums were added to memory incrementally during scanning;
        # add any remaining that weren't flushed yet, then do a final save.
        already_saved_n = getattr(self, '_local_last_saved_n', 0)
        remaining = albums[already_saved_n:]
        for album in remaining:
            self.add_album_to_memory(album)
        self.save_javdb_to_file()
        self.log(f'[LOCAL] DONE! {len(albums)} albums saved to my javdb.json')

    # ── Qt close ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.log('[EXIT] Closing application...')
        save_df(self.df_maglink, MAGLINK_FN)
        save_df(self.df_javdb,   JAVDB_FN)
        
        # Save PikPak token and close client
        if self.pikpak:
            self.save_pikpak_token()
            try:
                # Close the httpx client asynchronously in a temporary loop
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.pikpak.httpx_client.aclose())
                loop.close()
            except Exception as e:
                print(f'Error closing PikPak client: {e}')

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        event.accept()


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = JdbDownloader()
    
    # Handle Ctrl+C and other termination signals
    def signal_handler(sig, frame):
        print(f'\nSignal {sig} received, shutting down...')
        QTimer.singleShot(0, win.close)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    win.show()
    win._init_browser()
    win._init_clipboard_timer()
    sys.exit(app.exec())
