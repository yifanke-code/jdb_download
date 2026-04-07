#!/usr/bin/env python3
# coding=utf-8
import sys
import re
import os
import json
import random
import pandas as pd
import pyperclip
from pathlib import Path
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QCheckBox, 
    QGroupBox, QTextEdit, QScrollArea, QFrame, QMessageBox, QComboBox,
    QSpinBox, QButtonGroup, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QFileDialog
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import aria2p

ARIA2_SERVER = 'http://192.168.50.7'

def get_json_path(filename, fallback_dir='c:/github/my_json'):
    local = Path('./' + filename)
    fallback = Path(fallback_dir + '/' + filename)
    if local.exists():
        return local
    elif fallback.exists():
        return fallback
    return local

MAGLINK_FN = get_json_path('maglink_added.json')
JAVDB_FN = get_json_path('my javdb.json')
COLLECTION_FN = get_json_path('my collection.json')
CHECK_FN = get_json_path('check.json')

def load_check_json():
    if CHECK_FN.is_file():
        try:
            return pd.read_json(CHECK_FN)
        except:
            pass
    return pd.DataFrame(columns=['ID', 'check_date'])

def save_check_json(df):
    try:
        df.reset_index(drop=True, inplace=True)
        df.to_json(CHECK_FN, index=False)
    except Exception as e:
        print(f'Cannot write to {CHECK_FN}: {e}')

DELAYS = [10, 1, 3, 7, 2, 0.2, 18, 3, 6, 15, 5, 0.5, 0.1, 1, 6, 4, 2, 8, 12]

def my_delay():
    import time
    time.sleep(random.choice(DELAYS))

def safe_goto(page, url, retries=3):
    import time
    for i in range(retries):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(random.choice(DELAYS))
            return True
        except Exception as e:
            if 'interrupted by another navigation' in str(e):
                time.sleep(2)
                continue
            raise
    return False

def check_security_verification(source):
    patterns = [
        r'Security\s*Verification',
        r'驗證.*您的',
        r'robot\s*check',
        r'cloudflare.*challenge',
        r'Access\s+denied',
        r'Google\s*Recaptcha',
        r'cf.*verify',
        r'turnstile',
    ]
    for p in patterns:
        if re.search(p, source, re.IGNORECASE):
            return True
    return False

def load_json_safe(fn):
    if fn.is_file():
        try:
            return pd.read_json(fn)
        except:
            pass
    return pd.DataFrame()

def save_json_safe(df, fn):
    try:
        df.reset_index(drop=True, inplace=True)
        df.to_json(fn, index=False)
    except Exception as e:
        print(f'Cannot write to {fn}: {e}')

class AlbumInfo:
    def __init__(self, url, aid, release_date, has_magnet, actors, series, tags, rate, release, img_link, title=''):
        self.url = url
        self.aid = aid
        self.release_date = release_date
        self.has_magnet = has_magnet
        self.actors = actors
        self.series = series
        self.tags = tags
        self.rate = rate
        self.release = release
        self.img_link = img_link
        self.title = title
        self.magnet_links = []

class LocalScanWorker(QThread):
    log_signal = pyqtSignal(str)
    album_found_signal = pyqtSignal(object)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(list)
    
    def __init__(self, files, page, parent=None):
        super().__init__(parent)
        self.files = files
        self.page = page
        self.albums = []
        
    def run(self):
        total = len(self.files)
        for i, f in enumerate(self.files):
            try:
                filename = f.name
                aid = self.extract_id_from_filename(filename)
                
                if not aid:
                    self.log_signal.emit(f'[LOCAL] Cannot extract ID from: {filename}')
                    self.progress_signal.emit(i + 1, total)
                    continue
                    
                self.log_signal.emit(f'[LOCAL] Searching: {aid}')
                
                search_url = f'https://javdb.com/search?q={aid}&f=all'
                
                if not safe_goto(self.page, search_url):
                    self.log_signal.emit(f'[LOCAL] Failed to search: {aid}')
                    self.progress_signal.emit(i + 1, total)
                    continue
                    
                source = self.page.content()
                
                album_links = re.findall(r"<a\s{1}href=\"(/v/[0-9A-Za-z]+)\"", source)
                
                if not album_links:
                    self.log_signal.emit(f'[LOCAL] No album found: {aid}')
                    self.progress_signal.emit(i + 1, total)
                    continue
                    
                first_album_url = 'https://javdb.com' + album_links[0]
                self.log_signal.emit(f'[LOCAL] Found album: {first_album_url}')
                
                if not safe_goto(self.page, first_album_url):
                    self.log_signal.emit(f'[LOCAL] Failed to load album: {aid}')
                    self.progress_signal.emit(i + 1, total)
                    continue
                    
                source = self.page.content()
                
                items = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"current-title\">([^<]+)<", source)
                item2s = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"origin-title\">([^<]+)<", source)
                if item2s:
                    items = item2s
                    
                if not items:
                    self.log_signal.emit(f'[LOCAL] Cannot parse album: {aid}')
                    self.progress_signal.emit(i + 1, total)
                    continue
                    
                aid_from_page = items[0][0]
                title = items[0][1] if len(items[0]) > 1 else ''
                
                actors = re.findall(r"<a\s{1}href=\"/actors/([^\"]+)[^>]+>([^<]+)</a><strong\sclass=\"symbol\sfemale\">", source)
                series = re.findall(r"<a\shref=\"/series[^>]+>([^<]+)", source)
                tags = re.findall(r"<a\shref=\"/tags[^>]+>([^<]+)", source)
                rates = re.findall(r"((?<=&nbsp;)[0-9\.]+(?=分))", source)
                releases = re.findall(r"日期:[\w\W]+?class=\"value\">([^<]+)</span>", source)
                album_img_links = re.findall(r"class=\"video-meta-panel\"[\w\W]+?<img\ssrc=\"([^\"]+)\"\sclass=\"video-cover\"", source)
                
                img_link = album_img_links[0] if album_img_links else ''
                rate = rates[0] if rates else '0.0'
                release = releases[0] if releases else ''
                
                album = AlbumInfo(first_album_url, aid_from_page, release, True, actors, series, tags, rate, release, img_link, title)
                self.albums.append(album)
                self.log_signal.emit(f'[LOCAL] Added: {aid_from_page} - {title} ({len(actors)} actors)')
                
            except Exception as e:
                self.log_signal.emit(f'[LOCAL] Error: {e}')
            finally:
                self.progress_signal.emit(i + 1, total)
                
        self.finished_signal.emit(self.albums)
        
    def extract_id_from_filename(self, filename):
        filename = filename.upper()
        filename = re.sub(r'\.(MP4|MKV|AVI|MOV|WMV|FLV|WEBM|M4V|PRORES)$', '', filename)
        
        filename = re.sub(r'HHD800\.COM', '', filename)
        filename = re.sub(r'HHD800', '', filename)
            
        patterns = [
            r'([A-Z]{2,5}[-\s]?\d{3,5})',
            r'([A-Z]{1,2}\d{2,5})',
            r'([A-Z]+\d+)',
        ]
        for p in patterns:
            match = re.search(p, filename)
            if match:
                return match.group(1).replace(' ', '-')
        return None
        
class JdbDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('JAV DB Downloader')
        self.resize(1400, 900)
        
        self.playwright = None
        self.browser = None
        self.page = None
        
        try:
            self.aria2 = aria2p.API(
                aria2p.Client(host=ARIA2_SERVER, port=6800, secret="")
            )
        except:
            self.aria2 = None
            print('aria2 not available')
        
        self.df_maglink = load_json_safe(MAGLINK_FN)
        self.df_javdb = load_json_safe(JAVDB_FN)
        self.df_collection = load_json_safe(COLLECTION_FN)
        
        if not self.df_maglink.empty and 'id' in self.df_maglink.columns:
            self.downloaded_maglinks = set(self.df_maglink['id'].tolist())
        else:
            self.downloaded_maglinks = set()
            
        if not self.df_javdb.empty and 'ID' in self.df_javdb.columns:
            self.id_list = set(self.df_javdb['ID'].tolist())
            self.collection_ids = set(self.df_javdb.loc[self.df_javdb['AV'].str.contains('Collection', na=False), 'ID'].tolist())
        else:
            self.id_list = set()
            self.collection_ids = set()
            
        if not self.df_collection.empty and 'ID' in self.df_collection.columns:
            self.check_list = set(self.df_collection['ID'].tolist())
        else:
            self.check_list = set()
        
        self.df_check = load_check_json()
        if not self.df_check.empty and 'ID' in self.df_check.columns:
            self.checked_ids = set(self.df_check['ID'].tolist())
        else:
            self.checked_ids = set()
        
        self.current_page = 1
        self.current_album = None
        self.paused_album = None
        self.is_scanning = False
        self.page_to = 1
        self.base_url = 'https://javdb.com/censored'
        self.current_page_display = ''
        
        self.t_now = pd.Timestamp.now()
        self.t_h1year = self.t_now - pd.Timedelta(270, 'd')
        
        self.df_collection = load_json_safe(COLLECTION_FN)
        
        self._init_ui()
        self._init_browser()
        self._init_clipboard_timer()
        self._init_page_monitor()
        
    def _init_page_monitor(self):
        self.page_timer = QTimer(self)
        self.page_timer.timeout.connect(self.check_page_change)
        self.page_timer.start(1000)
        self.last_url = ''
        
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        top_layout = QHBoxLayout()
        
        page_group = QGroupBox('Page Range')
        page_layout = QVBoxLayout()
        self.radio_all_pages = QRadioButton('All Pages')
        self.radio_single_page = QRadioButton('Single Page')
        self.radio_page_range = QRadioButton('Page Range (from-to)')
        self.radio_all_pages.setChecked(True)
        
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel('From:'))
        self.spin_from = QSpinBox()
        self.spin_from.setValue(1)
        self.spin_from.setMaximum(9999)
        range_layout.addWidget(self.spin_from)
        range_layout.addWidget(QLabel('To:'))
        self.spin_to = QSpinBox()
        self.spin_to.setValue(1)
        self.spin_to.setMaximum(9999)
        range_layout.addWidget(self.spin_to)
        
        page_layout.addWidget(self.radio_all_pages)
        page_layout.addWidget(self.radio_single_page)
        page_layout.addWidget(self.radio_page_range)
        page_layout.addLayout(range_layout)
        page_group.setLayout(page_layout)
        
        url_group = QGroupBox('Search URL')
        url_layout = QVBoxLayout()
        
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel('Type:'))
        self.combo_search_type = QComboBox()
        self.combo_search_type.addItems(['censored', 'uncensored', 'search', 'actor'])
        self.combo_search_type.currentTextChanged.connect(self.on_search_type_changed)
        type_layout.addWidget(self.combo_search_type)
        type_layout.addWidget(QLabel('Value:'))
        self.line_search = QLineEdit()
        self.line_search.setText('https://javdb.com/censored')
        type_layout.addWidget(self.line_search)
        
        url_layout.addLayout(type_layout)
        url_group.setLayout(url_layout)
        
        direct_group = QGroupBox('Direct Album Link')
        direct_layout = QHBoxLayout()
        self.line_album_link = QLineEdit()
        self.line_album_link.setPlaceholderText('https://javdb.com/v/xxx')
        self.btn_go_album = QPushButton('Go to Album')
        self.btn_go_album.clicked.connect(self.go_to_album)
        direct_layout.addWidget(QLabel('Link:'))
        direct_layout.addWidget(self.line_album_link)
        direct_layout.addWidget(self.btn_go_album)
        direct_group.setLayout(direct_layout)
        
        local_group = QGroupBox('Scan Local Files')
        local_layout = QHBoxLayout()
        self.line_local_path = QLineEdit()
        self.line_local_path.setPlaceholderText('Select folder with video files...')
        self.btn_browse = QPushButton('Browse')
        self.btn_browse.clicked.connect(self.browse_local_folder)
        self.btn_scan_local = QPushButton('Scan Local Files')
        self.btn_scan_local.clicked.connect(self.scan_local_files)
        self.btn_stop_local = QPushButton('STOP')
        self.btn_stop_local.setEnabled(False)
        self.btn_stop_local.clicked.connect(self.stop_local_scan)
        self.progress_local = QProgressBar()
        self.progress_local.setVisible(False)
        local_layout.addWidget(QLabel('Path:'))
        local_layout.addWidget(self.line_local_path)
        local_layout.addWidget(self.btn_browse)
        local_layout.addWidget(self.btn_scan_local)
        local_layout.addWidget(self.btn_stop_local)
        local_group.setLayout(local_layout)
        
        self.progress_layout = QHBoxLayout()
        self.progress_layout.addWidget(self.progress_local)
        main_layout.addLayout(self.progress_layout)
        
        top_layout.addWidget(page_group)
        top_layout.addWidget(url_group)
        top_layout.addWidget(direct_group)
        top_layout.addWidget(local_group)
        
        filter_group = QGroupBox('Filters')
        filter_layout = QHBoxLayout()
        self.chk_new_legends_only = QCheckBox('-nl 新瓶舊酒/全部')
        self.chk_no_collection = QCheckBox('-nc 單人/含合集')
        self.chk_force_download_again = QCheckBox('-fda 重下載/未下載')
        self.chk_force_download_mag = QCheckBox('-fdm 不管近日有無下載/只有近日未下載')
        self.chk_force_download_old = QCheckBox('-fdo 不管老種子/只看新種子')
        self.chk_uncensored = QCheckBox('-uc 只停在-u/-c/-uc')
        self.chk_chinese = QCheckBox('-c 只停在-c')
        
        self.chk_new_legends_only.setChecked(True)
        self.chk_force_download_again.setChecked(True)
        self.chk_force_download_old.setChecked(True)
        self.chk_no_collection.setChecked(False)
        
        filter_layout.addWidget(self.chk_new_legends_only)
        filter_layout.addWidget(self.chk_no_collection)
        filter_layout.addWidget(self.chk_force_download_again)
        filter_layout.addWidget(self.chk_force_download_mag)
        filter_layout.addWidget(self.chk_force_download_old)
        filter_layout.addWidget(self.chk_uncensored)
        filter_layout.addWidget(self.chk_chinese)
        filter_group.setLayout(filter_layout)
        
        main_layout.addLayout(top_layout)
        main_layout.addWidget(filter_group)
        
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel('Download to:'))
        self.combo_dest = QComboBox()
        self.combo_dest.addItems(['aria2', 'pikpak'])
        dest_layout.addWidget(self.combo_dest)
        dest_layout.addStretch()
        main_layout.addLayout(dest_layout)
        
        control_layout = QHBoxLayout()
        self.btn_start = QPushButton('Start Scan')
        self.btn_pause = QPushButton('Pause (Wait Decision)')
        self.btn_continue = QPushButton('Continue to Next')
        self.btn_skip = QPushButton('Skip This Album')
        self.btn_download_mag = QPushButton('Download Magnet')
        self.btn_save_album = QPushButton('Save to W:/')
        self.btn_stop = QPushButton('STOP')
        
        self.btn_start.clicked.connect(self.start_scan)
        self.btn_pause.clicked.connect(self.pause_current)
        self.btn_continue.clicked.connect(self.continue_scan)
        self.btn_skip.clicked.connect(self.skip_current)
        self.btn_download_mag.clicked.connect(self.download_magnet)
        self.btn_save_album.clicked.connect(self.save_album_info)
        self.btn_stop.clicked.connect(self.stop_scan)
        
        self.btn_stop.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        
        control_layout.addWidget(self.btn_start)
        control_layout.addWidget(self.btn_pause)
        control_layout.addWidget(self.btn_continue)
        control_layout.addWidget(self.btn_skip)
        control_layout.addWidget(self.btn_download_mag)
        control_layout.addWidget(self.btn_save_album)
        control_layout.addWidget(self.btn_stop)
        main_layout.addLayout(control_layout)
        
        info_layout = QHBoxLayout()
        self.lbl_current_page = QLabel('Current Page: -')
        font_current = QFont()
        font_current.setPointSize(14)
        font_current.setBold(True)
        self.lbl_current_page.setFont(font_current)
        self.lbl_album = QLabel('Album: -')
        self.lbl_status = QLabel('Ready')
        info_layout.addWidget(self.lbl_current_page)
        info_layout.addWidget(self.lbl_album)
        info_layout.addWidget(self.lbl_status)
        main_layout.addLayout(info_layout)
        
        self.lbl_album_info = QLabel('')
        self.lbl_album_info.setStyleSheet("font-weight: bold; color: #0066cc;")
        main_layout.addWidget(self.lbl_album_info)
        
        self.table_album = QTableWidget()
        self.table_album.setColumnCount(6)
        self.table_album.setHorizontalHeaderLabels(['種子的title', '檔案大小', '高清', '字幕', '破解', '日期'])
        self.table_album.horizontalHeader().setStretchLastSection(False)
        self.table_album.setColumnWidth(0, 320)
        self.table_album.setColumnWidth(1, 70)
        self.table_album.setColumnWidth(2, 45)
        self.table_album.setColumnWidth(3, 45)
        self.table_album.setColumnWidth(4, 45)
        self.table_album.setColumnWidth(5, 85)
        self.table_album.cellDoubleClicked.connect(self.on_table_double_click)
        main_layout.addWidget(self.table_album)
        
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setMaximumHeight(200)
        main_layout.addWidget(self.text_output)
        
        self.lbl_info = QLabel('Waiting...')
        main_layout.addWidget(self.lbl_info)
        
    def _init_browser(self):
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
            ctx = self.browser.contexts[0]
            if ctx.pages:
                self.page = ctx.pages[0]
            else:
                self.page = ctx.new_page()
            self.log('Browser connected via CDP')
        except Exception as e:
            self.log(f'Browser connection failed: {e}')
            self.playwright = None
            self.browser = None
            
    def _init_clipboard_timer(self):
        self.clip_timer = QTimer(self)
        self.clip_timer.timeout.connect(self.check_clipboard)
        self.clip_timer.start(500)
        self.last_clip = ''
        
    def log(self, msg):
        self.text_output.append(str(msg))
        
    def get_page_range(self):
        if self.radio_all_pages.isChecked():
            return (1, 9999)
        elif self.radio_single_page.isChecked():
            p = self.spin_from.value()
            return (p, p)
        else:
            return (self.spin_from.value(), self.spin_to.value())
    
    def on_search_type_changed(self, text):
        if text == 'censored':
            self.line_search.setText('https://javdb.com/censored')
            self.line_search.setEnabled(True)
        elif text == 'uncensored':
            self.line_search.setText('https://javdb.com/uncensored')
            self.line_search.setEnabled(True)
        elif text == 'search':
            self.line_search.setText('')
            self.line_search.setPlaceholderText('Enter search keyword (e.g., abc)')
            self.line_search.setEnabled(True)
        elif text == 'actor':
            self.line_search.setText('')
            self.line_search.setPlaceholderText('Enter actor name or full link (e.g., gyRE)')
            self.line_search.setEnabled(True)
    
    def start_scan(self):
        if not self.browser:
            self.log('Browser not connected')
            return
            
        page_from, page_to = self.get_page_range()
        self.current_page = page_from
        self.page_to = page_to
        
        search_type = self.combo_search_type.currentText()
        value = self.line_search.text().strip()
        
        if search_type == 'censored':
            self.base_url = 'https://javdb.com/censored'
        elif search_type == 'uncensored':
            self.base_url = 'https://javdb.com/uncensored'
        elif search_type == 'search':
            self.base_url = f'https://javdb.com/search?q={value}&f=download'
        elif search_type == 'actor':
            if value.startswith('http'):
                self.base_url = value
            else:
                self.base_url = f'https://javdb.com/actors/{value}'
        else:
            self.base_url = value if value else 'https://javdb.com/censored'
            
        self.is_scanning = True
        self.btn_start.setEnabled(False)
        
        self.log(f'Starting scan: {self.base_url}, pages {self.current_page}-{self.page_to}')
        self.process_page()
        
    def process_page(self):
        if not self.is_scanning:
            return
            
        if self.current_page > self.page_to:
            self.log('=== Scan Completed ===')
            self.save_javdb_to_file()
            save_check_json(self.df_check)
            self.btn_start.setEnabled(True)
            self.is_scanning = False
            return
            
        self.lbl_current_page.setText(f'Current Page: {self.current_page}')
        self.current_page_display = f'Page {self.current_page}'
        page_url = f'{self.base_url}?page={self.current_page}'
        
        try:
            if not safe_goto(self.page, page_url):
                self.log(f'Error loading page: retry failed')
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
            self.is_scanning = False
            self.btn_start.setEnabled(True)
            self.lbl_status.setText('SECURITY VERIFICATION REQUIRED!')
            self.log('[PAUSE] ===== SECURITY VERIFICATION DETECTED =====')
            self.log('[PAUSE] Please complete the verification in browser, then press Continue')
            return
            
        links = re.findall(
            r"<a\s{1}href=\"([^\"]+(?=\"\sclass=\"box\")).+?((?<=<strong>)[^<]+)</stron.+?<div\sclass=\"meta\">\n\s+([^\n]+).+?((?<=<div\sclass=\"tags\shas-addons\">).+?(?=</div>))",
            source, flags=re.DOTALL
        )
        
        self.log(f'Page {self.current_page}: Found {len(links)} albums')
        
        if not links:
            self.log('No more albums, stopping')
            self.save_javdb_to_file()
            save_check_json(self.df_check)
            self.btn_start.setEnabled(True)
            self.is_scanning = False
            return
            
        self.albums_on_page = list(links)
        self.album_index = 0
        self.current_page += 1
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
        
        force_fda = self.chk_force_download_again.isChecked()
        if not force_fda and aid.upper() in self.check_list:
            self.log(f'[SKIP] {aid} already in collection (-fda not checked)')
            QTimer.singleShot(300, self.process_album)
            return
            
        nl = self.chk_new_legends_only.isChecked()
        if nl:
            try:
                if pd.Timestamp(release_dates) > self.t_h1year:
                    self.log(f'[SKIP] {aid} is new film ({release_dates}) > 270 days (-nl checked)')
                    QTimer.singleShot(300, self.process_album)
                    return
            except:
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
            self.is_scanning = False
            self.btn_start.setEnabled(True)
            self.lbl_status.setText('SECURITY VERIFICATION REQUIRED!')
            self.log('[PAUSE] ===== SECURITY VERIFICATION DETECTED =====')
            self.log('[PAUSE] Please complete the verification in browser, then press Continue')
            return
            
        items = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"current-title\">([^<]+)<", source)
        item2s = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"origin-title\">([^<]+)<", source)
        if item2s:
            items = item2s
            
        title = items[0][1] if items and len(items[0]) > 1 else ''
        
        actors = re.findall(r"<a\s{1}href=\"/actors/([^\"]+)[^>]+>([^<]+)</a><strong\sclass=\"symbol\sfemale\">", source)
        series = re.findall(r"<a\shref=\"/series[^>]+>([^<]+)", source)
        tags = re.findall(r"<a\shref=\"/tags[^>]+>([^<]+)", source)
        rates = re.findall(r"((?<=&nbsp;)[0-9\.]+(?=分))", source)
        releases = re.findall(r"日期:[\w\W]+?class=\"value\">([^<]+)</span>", source)
        album_img_links = re.findall(r"class=\"video-meta-panel\"[\w\W]+?<img\ssrc=\"([^\"]+)\"\sclass=\"video-cover\"", source)
        
        img_link = album_img_links[0] if album_img_links else ''
        rate = rates[0] if rates else '0.0'
        release = releases[0] if releases else ''
        
        self.current_album.actors = actors
        self.current_album.series = series
        self.current_album.tags = tags
        self.current_album.rate = rate
        self.current_album.release = release
        self.current_album.img_link = img_link
        self.current_album.title = title
        
        nc = self.chk_no_collection.isChecked()
        female_count = len(actors)
        if nc and female_count != 1:
            self.log(f'[SKIP] {aid} has {female_count} female actors (-nc checked, need exactly 1 to pause)')
            QTimer.singleShot(300, self.process_album)
            return
            
        soup = BeautifulSoup(source, 'html.parser')
        magnet_items = soup.find_all('div', class_='item')
        
        mag_links_raw = []
        for item in magnet_items:
            btn = item.find('button', {'data-clipboard-text': True})
            name_span = item.find('span', class_='name')
            meta_span = item.find('span', class_='meta')
            time_span = item.find('span', class_='time')
            
            if btn and btn.get('data-clipboard-text'):
                mag = btn['data-clipboard-text']
                title = name_span.get_text(strip=True) if name_span else ''
                meta = meta_span.get_text(strip=True) if meta_span else ''
                date = time_span.get_text(strip=True) if time_span else ''
                mag_links_raw.append((mag, title, meta, date))
        
        self.current_album.magnet_links = mag_links_raw
        
        if not mag_links_raw:
            self.log(f'[SKIP] {aid}: No magnets found')
            QTimer.singleShot(300, self.process_album)
            return
        
        uc_checked = self.chk_uncensored.isChecked()
        if uc_checked:
            has_uc_magnet = any(
                '-u' in m[1].lower() or '-c' in m[1].lower() or '-uc' in m[1].lower()
                for m in mag_links_raw
            )
            if not has_uc_magnet:
                self.log(f'[SKIP] {aid}: No -u/-c/-uc magnet found (-uc checked)')
                QTimer.singleShot(300, self.process_album)
                return
        
        if self.is_recently_checked(aid):
            reply = QMessageBox.question(
                self, 'Warning',
                f'Album {aid} was checked within 10 days.\nContinue to next?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                QTimer.singleShot(300, self.process_album)
                return
            
        self.display_album_info()
        
        aid = self.current_album.aid
        if not self.df_javdb.empty:
            id_list = set(self.df_javdb['ID'].tolist())
        else:
            id_list = set()
        if aid.upper() not in id_list:
            self.add_album_to_memory(self.current_album)
            self.log(f'[ADDED] {aid} to memory (scan pause)')
            
        self.check_collection_and_open_browser(aid)
        
        self.log(f'[PAUSE] {self.current_album.aid} - {self.current_page_display} - Reason: magnets found, waiting for decision')
        self.pause_current()
        
    def parse_magnet_info(self, mag_link):
        import urllib.parse
        
        try:
            parsed = urllib.parse.urlparse(mag_link)
            params = urllib.parse.parse_qs(parsed.query)
            
            dn = params.get('dn', [''])[0]
            dn_decoded = urllib.parse.unquote(dn)
            
            title = dn_decoded
            
            size = ''
            hd = ''
            subtitle = ''
            cracked = ''
            
            if '-u' in dn_decoded.lower() or '無碼' in dn_decoded or 'uncensored' in dn_decoded.lower():
                cracked = '是'
            
            if '-c' in dn_decoded.lower() or '中文' in dn_decoded or '字幕' in dn_decoded:
                subtitle = '是'
            
            if '高清' in dn_decoded or '720p' in dn_decoded.lower() or '1080p' in dn_decoded.lower() or '4k' in dn_decoded.lower() or 'hd' in dn_decoded.lower():
                hd = '是'
                
            size_match = re.search(r'\[(\d+\.?\d*\s*[GMgm])\]', dn_decoded)
            if size_match:
                size = size_match.group(1)
            
            return title, size, hd, subtitle, cracked
            
        except:
            return mag_link[:50], '', '', '', ''
            
    def display_album_info(self):
        self.table_album.setRowCount(0)
        
        mag_data = []
        for item in self.current_album.magnet_links:
            if len(item) >= 4:
                mag, title, meta, date = item[:4]
                tag = ''
            elif len(item) >= 3:
                mag, title, meta = item[:3]
                tag = ''
                date = ''
            else:
                continue
            
            size = meta.split(',')[0].strip() if meta else ''
            
            hd = '高清' if 'hd' in title.lower() else ''
            subtitle = '字幕' if '-c' in title.lower() or '字幕' in title else ''
            cracked = '破解' if '-u' in title.lower() or '無碼' in title or 'uncensored' in title.lower() else ''
            
            mag_data.append({
                'mag': mag, 'date': date, 'title': title, 
                'size': size, 'hd': hd, 'subtitle': subtitle, 'cracked': cracked
            })
        
        def parse_size(s):
            if not s:
                return 0
            s = s.upper().strip()
            if 'G' in s:
                try:
                    return float(re.sub(r'[^\d.]', '', s)) * 1024
                except:
                    return 0
            elif 'M' in s:
                try:
                    return float(re.sub(r'[^\d.]', '', s))
                except:
                    return 0
            return 0
        
        def sort_key(x):
            cracked_val = 1 if x['cracked'] == '破解' else 0
            subtitle_val = 1 if x['subtitle'] == '字幕' else 0
            hd_val = 1 if x['hd'] == '高清' else 0
            size_val = parse_size(x['size'])
            return (-cracked_val, -subtitle_val, -hd_val, -size_val, x['date'])
            
        mag_data.sort(key=sort_key)
        
        self.magnet_list = []
        
        for md in mag_data:
            row = self.table_album.rowCount()
            self.table_album.insertRow(row)
            
            self.table_album.setItem(row, 0, QTableWidgetItem(md['title'][:50]))
            self.table_album.setItem(row, 1, QTableWidgetItem(md['size']))
            self.table_album.setItem(row, 2, QTableWidgetItem(md['hd']))
            self.table_album.setItem(row, 3, QTableWidgetItem(md['subtitle']))
            self.table_album.setItem(row, 4, QTableWidgetItem(md['cracked']))
            self.table_album.setItem(row, 5, QTableWidgetItem(md['date']))
            
            self.magnet_list.append(md['mag'])
            
        actors_str = ''
        if self.current_album.actors:
            if len(self.current_album.actors) > 1:
                actors_str = 'Collection (' + str(len(self.current_album.actors)) + '人)'
            else:
                actors_str = self.current_album.actors[0][1]
        
        album_info_text = f"Actors: {actors_str} | Title: {self.current_album.title[:30] if self.current_album.title else ''} | Release: {self.current_album.release_date}"
        self.lbl_album_info.setText(album_info_text)
        
        info = f"ID: {self.current_album.aid} | Rate: {self.current_album.rate}"
        if self.current_album.series:
            info += f" | Series: {self.current_album.series[0]}"
            
        self.lbl_info.setText(f'{self.current_page_display} | {info}')
        self.log(f'[TABLE] {len(mag_data)} magnets for {self.current_album.aid}')
        
    def on_table_double_click(self, row, col):
        if row < len(self.magnet_list):
            mag = self.magnet_list[row]
            pyperclip.copy(mag)
            self.log(f'[COPY] Magnet copied to clipboard: {mag[:50]}...')
            
            dest = self.combo_dest.currentText()
            if dest == 'aria2' and self.aria2:
                try:
                    ks = self.aria2.get_global_options()
                    download = self.aria2.add_magnet(mag, options=ks)
                    self.log(f'[DL] Added to aria2: {download.gid}')
                except Exception as e:
                    self.log(f'[DL] aria2 error: {e}')
        
    def pause_current(self):
        self.paused_album = self.current_album
        self.log(f'Paused: {self.current_album.aid}')
        
    def is_recently_checked(self, aid):
        if self.df_check.empty or 'ID' not in self.df_check.columns:
            return False
        aid_upper = aid.upper()
        df_album = self.df_check[self.df_check['ID'].str.upper() == aid_upper]
        if df_album.empty:
            return False
        try:
            check_date = pd.to_datetime(df_album['check_date'].iloc[0])
            days_since = (pd.Timestamp.now() - check_date).days
            return days_since <= 10
        except:
            return False
        
    def save_to_check_json(self, aid):
        aid_upper = aid.upper()
        if self.df_check.empty:
            self.df_check = pd.DataFrame(columns=['ID', 'check_date'])
        
        existing = self.df_check[self.df_check['ID'].str.upper() == aid_upper]
        if not existing.empty:
            self.df_check = self.df_check[self.df_check['ID'].str.upper() != aid_upper]
        
        new_row = pd.DataFrame([{
            'ID': aid_upper,
            'check_date': pd.Timestamp.now().strftime('%Y-%m-%d')
        }])
        self.df_check = pd.concat([self.df_check, new_row], ignore_index=True)
        save_check_json(self.df_check)
        
    def continue_scan(self):
        if self.paused_album:
            self.save_to_check_json(self.paused_album.aid)
            self.add_album_to_memory(self.paused_album)
        self.log(f'[CONTINUE] {self.paused_album.aid if self.paused_album else ""} - proceeding to next album')
        QTimer.singleShot(300, self.process_album)
        
    def skip_current(self):
        self.log(f'[SKIP BTN] {self.paused_album.aid if self.paused_album else ""} - manually skipped by user')
        QTimer.singleShot(300, self.process_album)
        
    def stop_scan(self):
        self.is_scanning = False
        self.btn_start.setEnabled(True)
        self.lbl_status.setText('STOPPED - Ready for new scan')
        self.lbl_current_page.setText('Current Page: -')
        self.save_javdb_to_file()
        save_check_json(self.df_check)
        self.log('[STOP] Scan stopped by user. Ready for new scan.')
        
    def go_to_album(self):
        if not self.browser:
            self.log('Browser not connected')
            return
            
        link = self.line_album_link.text().strip()
        if not link:
            self.log('Please enter album link')
            return
            
        if not link.startswith('http'):
            link = 'https://javdb.com/v/' + link
            
        self.log(f'Loading album: {link}')
        
        try:
            if not safe_goto(self.page, link):
                self.log('Failed to load album')
                return
            source = self.page.content()
        except Exception as e:
            self.log(f'Error loading album: {e}')
            return
            
        if check_security_verification(source):
            self.log('[PAUSE] ===== SECURITY VERIFICATION DETECTED =====')
            self.lbl_status.setText('SECURITY VERIFICATION REQUIRED!')
            return
        
        items = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"current-title\">([^<]+)<", source)
        item2s = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"origin-title\">([^<]+)<", source)
        if item2s:
            items = item2s
            
        actors = re.findall(r"<a\s{1}href=\"/actors/([^\"]+)[^>]+>([^<]+)</a><strong\sclass=\"symbol\sfemale\">", source)
        series = re.findall(r"<a\shref=\"/series[^>]+>([^<]+)", source)
        tags = re.findall(r"<a\shref=\"/tags[^>]+>([^<]+)", source)
        rates = re.findall(r"((?<=&nbsp;)[0-9\.]+(?=分))", source)
        releases = re.findall(r"日期:[\w\W]+?class=\"value\">([^<]+)</span>", source)
        album_img_links = re.findall(r"class=\"video-meta-panel\"[\w\W]+?<img\ssrc=\"([^\"]+)\"\sclass=\"video-cover\"", source)
        
        img_link = album_img_links[0] if album_img_links else ''
        rate = rates[0] if rates else '0.0'
        release = releases[0] if releases else ''
        
        if not items:
            self.log('Cannot find album ID')
            return
            
        aid = items[0][0]
        title = items[0][1] if len(items[0]) > 1 else ''
        
        self.log(f'Album: {aid} - {title}')
        
        if not self.df_javdb.empty:
            id_list = set(self.df_javdb['ID'].tolist())
        else:
            id_list = set()
            
        already_exists = aid.upper() in id_list
        
        if not already_exists:
            self.add_album_to_memory(AlbumInfo(link, aid, '', True, actors, series, tags, rate, release, img_link, title))
            self.log(f'[ADDED] {aid} to my javdb.json (memory only)')
        else:
            self.log(f'[EXISTS] {aid} already in my javdb.json')
            
        self.check_collection_and_open_browser(aid)
            
        self.current_album = AlbumInfo(link, aid, release, True, actors, series, tags, rate, release, img_link, title)
        
        soup = BeautifulSoup(source, 'html.parser')
        magnet_items = soup.find_all('div', class_='item')
        
        mag_links_raw = []
        for item in magnet_items:
            btn = item.find('button', {'data-clipboard-text': True})
            name_span = item.find('span', class_='name')
            meta_span = item.find('span', class_='meta')
            time_span = item.find('span', class_='time')
            
            if btn and btn.get('data-clipboard-text'):
                mag = btn['data-clipboard-text']
                title = name_span.get_text(strip=True) if name_span else ''
                meta = meta_span.get_text(strip=True) if meta_span else ''
                date = time_span.get_text(strip=True) if time_span else ''
                mag_links_raw.append((mag, title, meta, date))
        
        self.current_album.magnet_links = mag_links_raw
        self.paused_album = self.current_album
        
        self.display_album_info()
        self.lbl_status.setText(f'Album: {aid}')
        
        self.check_clipboard_and_download()
        
    def convert_linux_to_windows_path(self, linux_path):
        if not linux_path:
            return None
            
        mapping = {
            '/volume1/aria2': 'w:/',
            '/volume2/Media_on': 'g:/',
            '/volume1/home/admin/18': 'p:/18',
            '/volume1/home/admin/Media': 'j:/',
        }
        
        for linux_prefix, win_prefix in mapping.items():
            if linux_path.startswith(linux_prefix):
                result = linux_path.replace(linux_prefix, win_prefix)
                result = result.replace('//', '/')
                return result
                
        return linux_path
        
    def check_collection_and_open_browser(self, aid):
        if self.df_collection.empty or 'ID' not in self.df_collection.columns:
            self.log(f'[COLLECTION] df_collection is empty or has no ID column')
            return
            
        aid_upper = aid.upper()
        collection_row = self.df_collection[self.df_collection['ID'].str.upper() == aid_upper]
        
        if collection_row.empty:
            self.log(f'[COLLECTION] {aid} not found in collection')
            return
        
        try:
            path_val = collection_row['path'].iloc[0] if 'path' in collection_row.columns else None
        except:
            path_val = None
        
        if not path_val:
            self.log(f'[COLLECTION] {aid} found but no path field')
            return
        
        win_path = self.convert_linux_to_windows_path(path_val)
        self.log(f'[COLLECTION] Win path: {win_path}')
        
        import subprocess
        import os
        try:
            if os.path.exists(win_path):
                subprocess.Popen(f'explorer /select,"{win_path}"')
                self.log(f'[COLLECTION] Opened folder: {win_path}')
            else:
                folder = os.path.dirname(win_path)
                if os.path.exists(folder):
                    subprocess.Popen(f'explorer "{folder}"')
                    self.log(f'[COLLECTION] Opened folder (file not found): {folder}')
                else:
                    self.log(f'[COLLECTION] Path does not exist: {folder}')
        except Exception as e:
            self.log(f'[COLLECTION] Failed to open: {e}')
        
    def check_clipboard_and_download(self):
        dest = self.combo_dest.currentText()
        
        try:
            cur = pyperclip.paste()
        except:
            return
            
        mag_pattern = r'(magnet:\?[^\s\n]+)'
        mag_links = re.findall(mag_pattern, cur)
        
        if mag_links:
            self.log(f'[CLIPBOARD] Found {len(mag_links)} magnet link(s) in clipboard')
            
            if dest == 'pikpak':
                self.log('[CLIPBOARD] pikpak mode - skipping aria2, just log the magnet')
            else:
                self.log(f'[CLIPBOARD] Destination: {dest}')
                
            for mag in mag_links:
                mag_clean = self.decode_html_entities(mag)
                self.log(f'[CLIPBOARD] Magnet: {mag_clean[:50]}...')
                
                if dest == 'aria2' and self.aria2:
                    try:
                        download = self.aria2.add_magnet(mag_clean)
                        self.log(f'[CLIPBOARD] Added to aria2: {download.gid}')
                    except Exception as e:
                        self.log(f'[CLIPBOARD] aria2 error: {e}')
                        
                new_row = pd.DataFrame([{
                    'id': mag_clean,
                    'cast': '',
                    'date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                    'title': '',
                    'maglink': mag_clean
                }])
                self.df_maglink = pd.concat([self.df_maglink, new_row], ignore_index=True)
                save_json_safe(self.df_maglink, MAGLINK_FN)
                
            self.log('[CLIPBOARD] Magnet(s) processed')
            pyperclip.copy('')
            
    def browse_local_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder with Videos')
        if folder:
            self.line_local_path.setText(folder)
            
    def extract_id_from_filename(self, filename):
        filename = filename.upper()
        filename = re.sub(r'\.(MP4|MKV|AVI|MOV|WMV|FLV|WEBM|M4V|PRORES)$', '', filename)
        
        filename = re.sub(r'HHD800\.COM', '', filename)
        filename = re.sub(r'HHD800', '', filename)
            
        patterns = [
            r'([A-Z]{2,5}[-\s]?\d{3,5})',
            r'([A-Z]{1,2}\d{2,5})',
            r'([A-Z]+\d+)',
        ]
        for p in patterns:
            match = re.search(p, filename)
            if match:
                return match.group(1).replace(' ', '-')
        return None
        
    def scan_local_files(self):
        if not self.browser:
            self.log('Browser not connected')
            return
            
        folder = self.line_local_path.text().strip()
        if not folder or not Path(folder).exists():
            self.log('Please select a valid folder')
            return
            
        video_exts = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v')
        files = [f for f in Path(folder).rglob('*') if f.is_file() and f.suffix.lower() in video_exts]
        
        if not files:
            self.log('No video files found in folder or subfolders')
            return
            
        self.log(f'[LOCAL] Found {len(files)} video files (including subfolders)')
        
        self.btn_scan_local.setEnabled(False)
        self.btn_stop_local.setEnabled(True)
        self.progress_local.setVisible(True)
        self.progress_local.setMaximum(len(files))
        self.progress_local.setValue(0)
        
        self.local_worker = LocalScanWorker(files, self.page)
        self.local_worker.log_signal.connect(self.log)
        self.local_worker.progress_signal.connect(self.on_local_progress)
        self.local_worker.finished_signal.connect(self.on_local_finished)
        self.local_worker.start()
        
    def stop_local_scan(self):
        if hasattr(self, 'local_worker') and self.local_worker.isRunning():
            self.local_worker.terminate()
            self.log('[LOCAL] Scan stopped by user')
            self.btn_scan_local.setEnabled(True)
            self.btn_stop_local.setEnabled(False)
            self.progress_local.setVisible(False)
            
    def on_local_progress(self, current, total):
        self.progress_local.setValue(current)
        
    def on_local_finished(self, albums):
        self.btn_scan_local.setEnabled(True)
        self.btn_stop_local.setEnabled(False)
        self.progress_local.setVisible(False)
        
        if not albums:
            self.log('[LOCAL] No albums found')
            return
            
        self.log(f'[LOCAL] Total: {len(albums)} albums, saving to my javdb.json...')
        
        for album in albums:
            self.add_album_to_memory(album)
            
        self.save_javdb_to_file()
        self.log(f'[LOCAL] DONE! {len(albums)} albums saved to my javdb.json')
            
    def download_magnet(self):
        if not self.paused_album:
            return
            
        for mag, _ in self.paused_album.magnet_links:
            mag_clean = self.decode_html_entities(mag)
            
            if self.aria2:
                try:
                    avid_i = str(random.random())
                    dl_path = Path("/volume1/aria2/_dl") / avid_i
                    dl_path_pc = Path("w:/_dl") / avid_i
                    
                    if dl_path_pc.parent.exists() or True:
                        ks = self.aria2.get_global_options()
                        ks.dir = str(dl_path).replace('\\', '/')
                        
                        download = self.aria2.add_magnet(mag_clean, options=ks)
                        self.log(f'Added to aria2: {download.gid}')
                        
                        new_row = pd.DataFrame([{
                            'id': mag_clean,
                            'cast': '',
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'title': '',
                            'maglink': mag_clean
                        }])
                        self.df_maglink = pd.concat([self.df_maglink, new_row], ignore_index=True)
                        self.downloaded_maglinks.add(mag_clean)
                        
                except Exception as e:
                    self.log(f'aria2 error: {e}')
                    
        save_json_safe(self.df_maglink, MAGLINK_FN)
        self.log('Magnet(s) saved to maglink_added.json')
        
    def add_album_to_memory(self, album):
        if not album:
            return
            
        aid = album.aid
        actors = album.actors
        
        self.df_javdb = self.df_javdb[self.df_javdb['ID'].str.upper() != aid.upper()]
        
        def strip_list(lst):
            if isinstance(lst, list):
                return [str(x).strip() if x else '' for x in lst]
            return lst
            
        for alink, actor in actors:
            if len(actors) > 1:
                av = 'Collection'
            else:
                av = str(actor).strip() if actor else ''
                
            av_list = [av.strip() if av else '', album.title.strip() if album.title else '', 0, 0, 0, aid.upper().strip(), actor[1].strip() if actor else '', 
                      album.img_link.strip() if album.img_link else '', album.rate.strip() if album.rate else '',
                      [s.strip() for s in album.series] if album.series else [], [t.strip() for t in album.tags] if album.tags else [],
                      actors, album.release.strip() if album.release else '']
            
            new_row = pd.DataFrame([av_list], columns=['AV', 'Album', 'count', 'size', 'path', 'ID', 'Cast', 'album_img_link', 'rate', 'series', 'tags', 'actors', 'release'])
            self.df_javdb = pd.concat([self.df_javdb, new_row], ignore_index=True)
            
        self.log(f'[ADDED] {aid} | title: {album.title[:30] if album.title else "(empty)"} to memory')
        
    def save_javdb_to_file(self):
        save_json_safe(self.df_javdb, JAVDB_FN)
        self.log('[SAVED] my javdb.json saved to disk')
        
    def save_album_info(self):
        self.save_javdb_to_file()
        
        import shutil
        
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
        
    def check_page_change(self):
        try:
            if not self.browser:
                return
                
            ctx = self.browser.contexts[0] if self.browser.contexts else None
            if not ctx or not ctx.pages:
                return
                
            self.page = ctx.pages[0]
            
            if not self.page:
                return
            
            current_url = self.page.url
            if not current_url:
                return
                
            url_str = str(current_url)
            
            if url_str == self.last_url:
                return
                
            self.last_url = url_str
            
            if '/v/' not in url_str or 'hhd800.com' in url_str:
                self.log(f'[PAGE] Non-album URL: {url_str}')
                return
            
            self.log(f'[PAGE] Album page detected: {url_str}')
            
            try:
                source = self.page.content()
            except Exception as e:
                self.log(f'[PAGE] Failed to get content: {e}')
                return
                
            items = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"current-title\">([^<]+)<", source)
            item2s = re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"origin-title\">([^<]+)<", source)
            if item2s:
                items = item2s
                
            actors = re.findall(r"<a\s{1}href=\"/actors/([^\"]+)[^>]+>([^<]+)</a><strong\sclass=\"symbol\sfemale\">", source)
            series = re.findall(r"<a\shref=\"/series[^>]+>([^<]+)", source)
            tags = re.findall(r"<a\shref=\"/tags[^>]+>([^<]+)", source)
            rates = re.findall(r"((?<=&nbsp;)[0-9\.]+(?=分))", source)
            releases = re.findall(r"日期:[\w\W]+?class=\"value\">([^<]+)</span>", source)
            album_img_links = re.findall(r"class=\"video-meta-panel\"[\w\W]+?<img\ssrc=\"([^\"]+)\"\sclass=\"video-cover\"", source)
            
            img_link = album_img_links[0] if album_img_links else ''
            rate = rates[0] if rates else '0.0'
            release = releases[0] if releases else ''
            title = items[0][1] if items and len(items[0]) > 1 else ''
            
            if not items:
                self.log('[PAGE] No items found in page')
                return
                
            aid = items[0][0]
            
            soup = BeautifulSoup(source, 'html.parser')
            magnet_items = soup.find_all('div', class_='item')
            
            mag_links_raw = []
            for item in magnet_items:
                btn = item.find('button', {'data-clipboard-text': True})
                name_span = item.find('span', class_='name')
                meta_span = item.find('span', class_='meta')
                time_span = item.find('span', class_='time')
                
                if btn and btn.get('data-clipboard-text'):
                    mag = btn['data-clipboard-text']
                    title = name_span.get_text(strip=True) if name_span else ''
                    meta = meta_span.get_text(strip=True) if meta_span else ''
                    date = time_span.get_text(strip=True) if time_span else ''
                    mag_links_raw.append((mag, title, meta, date))
            
            self.current_album = AlbumInfo(url_str, aid, release, True, actors, series, tags, rate, release, img_link, title)
            self.current_album.magnet_links = mag_links_raw
            self.paused_album = self.current_album
            
            self.display_album_info()
            self.log(f'[PAGE] Updated table with {len(mag_links_raw)} magnets for {aid}')
            
        except Exception as e:
            self.log(f'[PAGE] Error: {e}')
        
    def check_clipboard(self):
        if not self.is_scanning:
            return
            
        try:
            cur = pyperclip.paste()
        except:
            return
            
        if cur == self.last_clip or not cur:
            return
            
        self.last_clip = cur
        
        mag_pattern = r'(magnet:\?[^\s\n]+)'
        javdb_album_pattern = r'(https://javdb\.com/v/[0-9A-Za-z]+)'
        
        mag_links = re.findall(mag_pattern, cur)
        album_links = re.findall(javdb_album_pattern, cur)
        
        if mag_links:
            self.handle_magnet_from_clipboard(mag_links)
        elif album_links:
            self.handle_album_from_clipboard(album_links)
            
    def handle_magnet_from_clipboard(self, mag_links):
        for mag in mag_links:
            mag_clean = self.decode_html_entities(mag)
            
            if mag_clean in self.downloaded_maglinks and not self.chk_force_download_mag.isChecked():
                self.log(f'[Clipboard] Already downloaded: {mag_clean[:40]}...')
                continue
                
            self.log(f'[Clipboard] Adding magnet: {mag_clean[:40]}...')
            
            if self.current_album and self.current_album.aid:
                aid = self.current_album.aid
                if not self.df_javdb.empty:
                    id_list = set(self.df_javdb['ID'].tolist())
                else:
                    id_list = set()
                if aid.upper() not in id_list:
                    self.add_album_to_memory(self.current_album)
                    self.log(f'[Clipboard] Album {aid} added to memory')
            
            if self.aria2:
                try:
                    ks = self.aria2.get_global_options()
                    download = self.aria2.add_magnet(mag_clean, options=ks)
                    self.log(f'[Clipboard] Added: {download.gid}')
                except Exception as e:
                    self.log(f'[Clipboard] aria2 error: {e}')
                    
            new_row = pd.DataFrame([{
                'id': mag_clean,
                'cast': '',
                'date': datetime.now().strftime('%Y-%m-%d'),
                'title': '',
                'maglink': mag_clean
            }])
            self.df_maglink = pd.concat([self.df_maglink, new_row], ignore_index=True)
            self.downloaded_maglinks.add(mag_clean)
            
            save_json_safe(self.df_maglink, MAGLINK_FN)
            self.log('[Clipboard] Magnet saved')
            
    def handle_album_from_clipboard(self, album_links):
        for link in album_links:
            self.log(f'[Clipboard] Album link: {link}')
            
    def decode_html_entities(self, text):
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        return text
            
    def closeEvent(self, event):
        save_json_safe(self.df_maglink, MAGLINK_FN)
        save_json_safe(self.df_javdb, JAVDB_FN)
        
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
                
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = JdbDownloader()
    win.show()
    sys.exit(app.exec())