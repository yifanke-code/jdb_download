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
from playwright.sync_api import sync_playwright
import aria2p

ARIA2_SERVER = 'http://192.168.50.7'
MAGLINK_FN = Path('./maglink_added.json')
JAVDB_FN = Path('./my javdb.json')
COLLECTION_FN = Path('./my collection.json')
CHECK_FN = Path('./check.json')

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
    def __init__(self, url, aid, release_date, has_magnet, actors, series, tags, rate, release, img_link):
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
        self.magnet_links = []

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
        
        self._init_ui()
        self._init_browser()
        self._init_clipboard_timer()
        
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
        type_layout.addWidget(self.combo_search_type)
        type_layout.addWidget(QLabel('Value:'))
        self.line_search = QLineEdit()
        self.line_search.setText('https://javdb.com/censored')
        type_layout.addWidget(self.line_search)
        
        url_layout.addLayout(type_layout)
        url_group.setLayout(url_layout)
        
        top_layout.addWidget(page_group)
        top_layout.addWidget(url_group)
        
        filter_group = QGroupBox('Filters')
        filter_layout = QHBoxLayout()
        self.chk_new_legends_only = QCheckBox('-nl (New Legends Only)')
        self.chk_no_collection = QCheckBox('-nc (No Collection)')
        self.chk_force_download_again = QCheckBox('-fda (Force DL Album in Collection)')
        self.chk_force_download_mag = QCheckBox('-fdm (Force DL Mag)')
        self.chk_force_download_old = QCheckBox('-fdo (Force DL Old Seeds)')
        self.chk_uncensored = QCheckBox('-uc (Uncensored)')
        self.chk_chinese = QCheckBox('-c (Chinese)')
        
        self.chk_new_legends_only.setChecked(True)
        self.chk_force_download_again.setChecked(True)
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
        
        control_layout = QHBoxLayout()
        self.btn_start = QPushButton('Start Scan')
        self.btn_pause = QPushButton('Pause (Wait Decision)')
        self.btn_continue = QPushButton('Continue to Next')
        self.btn_skip = QPushButton('Skip This Album')
        self.btn_download_mag = QPushButton('Download Magnet')
        self.btn_save_album = QPushButton('Save Album Info')
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
        
        self.table_album = QTableWidget()
        self.table_album.setColumnCount(5)
        self.table_album.setHorizontalHeaderLabels(['Magnet Link', 'Date', 'Actor', 'ID', 'Release'])
        self.table_album.horizontalHeader().setStretchLastSection(True)
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
    
    def start_scan(self):
        if not self.browser:
            self.log('Browser not connected')
            return
            
        page_from, page_to = self.get_page_range()
        self.current_page = page_from
        self.page_to = page_to
        self.base_url = self.line_search.text().strip()
        if not self.base_url.startswith('http'):
            self.base_url = 'https://javdb.com/' + self.base_url
            
        self.is_scanning = True
        self.btn_start.setEnabled(False)
        
        self.log(f'Starting scan: {self.base_url}, pages {self.current_page}-{self.page_to}')
        self.process_page()
        
    def process_page(self):
        if not self.is_scanning:
            return
            
        if self.current_page > self.page_to:
            self.log('=== Scan Completed ===')
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
            
        nc = self.chk_no_collection.isChecked()
        if nc and aid.upper() in self.collection_ids:
            self.log(f'[SKIP] {aid} is Collection album (-nc checked)')
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
        
        nc = self.chk_no_collection.isChecked()
        if nc and len(actors) > 1:
            self.log(f'[SKIP] {aid} has {len(actors)} actors = Collection (-nc checked)')
            QTimer.singleShot(300, self.process_album)
            return
            
        mag_links_raw = re.findall(r"<a\shref=\"(magnet:[^\"]+(?=\"\stitle=)).+?((?<=class=\"time\">)[^<]+)", source, flags=re.DOTALL)
        
        fdo = self.chk_force_download_old.isChecked()
        nm = self.chk_uncensored.isChecked()
        cc = self.chk_chinese.isChecked()
        uc = nm or cc
        
        valid_mags = []
        skip_reasons = []
        
        for mag_link, mag_date in mag_links_raw:
            reason = None
            
            if not fdo:
                try:
                    if pd.Timestamp(mag_date) < self.t_h1year:
                        reason = 'seed too old'
                except:
                    pass
                    
            if uc and not reason:
                has_uc = ('-u' in mag_link.lower()) or ('-c' in mag_link.lower())
                if not has_uc:
                    reason = '-uc/-c filter not matched'
                    
            if mag_link in self.downloaded_maglinks and not self.chk_force_download_mag.isChecked():
                reason = 'already downloaded (-fdm not checked)'
                
            if not reason:
                valid_mags.append((mag_link, mag_date))
            else:
                skip_reasons.append(f'{mag_link[:30]}... reason: {reason}')
            
        self.current_album.magnet_links = valid_mags
        
        if skip_reasons:
            for sr in skip_reasons[:3]:
                self.log(f'[MAG SKIP] {sr}')
                
        if not valid_mags:
            self.log(f'[SKIP] {aid}: No valid magnets after filtering')
            QTimer.singleShot(300, self.process_album)
            return
        
        if self.is_recently_checked(aid):
            self.log(f'[AUTO-SKIP] {aid} was checked within 10 days, skipping pause')
            QTimer.singleShot(300, self.process_album)
            return
            
        self.display_album_info()
        self.log(f'[PAUSE] {self.current_album.aid} - {self.current_page_display} - Reason: magnets found, waiting for decision')
        self.pause_current()
        
    def display_album_info(self):
        self.table_album.setRowCount(0)
        
        for mag, date in self.current_album.magnet_links:
            row = self.table_album.rowCount()
            self.table_album.insertRow(row)
            self.table_album.setItem(row, 0, QTableWidgetItem(mag[:60] + '...'))
            self.table_album.setItem(row, 1, QTableWidgetItem(date))
            
            if len(self.current_album.actors) > 1:
                actor = 'Collection'
            elif self.current_album.actors:
                actor = self.current_album.actors[0][1]
            else:
                actor = ''
            self.table_album.setItem(row, 2, QTableWidgetItem(actor))
            self.table_album.setItem(row, 3, QTableWidgetItem(self.current_album.aid))
            self.table_album.setItem(row, 4, QTableWidgetItem(self.current_album.release_date))
            
        info = f"ID: {self.current_album.aid} | Release: {self.current_album.release_date} | Rate: {self.current_album.rate}"
        if self.current_album.series:
            info += f" | Series: {self.current_album.series[0]}"
        if self.current_album.actors:
            actors_str = ', '.join([a[1] for a in self.current_album.actors])
            info += f" | Actors: {actors_str}"
            
        self.lbl_info.setText(f'{self.current_page_display} | {info}')
        self.log(f'[TABLE] {len(self.current_album.magnet_links)} magnets for {self.current_album.aid}')
        
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
            self.log(f'[CONTINUE] {self.paused_album.aid} - saved to check.json')
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
        self.log('[STOP] Scan stopped by user. Ready for new scan.')
        
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
        
    def save_album_info(self):
        if not self.paused_album:
            return
            
        aid = self.paused_album.aid
        actors = self.paused_album.actors
        
        if not self.df_javdb.empty:
            id_list = set(self.df_javdb['ID'].tolist())
        else:
            id_list = set()
            
        if aid.upper() in id_list:
            self.log(f'{aid} already in my javdb')
            return
            
        for alink, actor in actors:
            if len(actors) > 1:
                av = 'Collection'
            else:
                av = actor
                
            av_list = [av, '', 0, 0, 0, aid.upper(), actor, 
                      self.paused_album.img_link, self.paused_album.rate,
                      self.paused_album.series, self.paused_album.tags,
                      actors, self.paused_album.release]
            
            new_row = pd.DataFrame([av_list], columns=['AV', 'Album', 'count', 'size', 'path', 'ID', 'Cast', 'album_img_link', 'rate', 'series', 'tags', 'actors', 'release'])
            self.df_javdb = pd.concat([self.df_javdb, new_row], ignore_index=True)
            
        save_json_safe(self.df_javdb, JAVDB_FN)
        self.log(f'Album {aid} saved to my javdb.json')
        
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