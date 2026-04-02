#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
"""
JAV Database URL Clipboard Manager
Monitors clipboard for JAV database URLs and magnet links, manages them in a local SQLite database,
and exports command sequences for batch operations.
"""

import sys
import logging
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtCore import QTimer
import re
import pyperclip

from copy_2_aj_form import Ui_MainWindow

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Regex patterns for URL and link matching
JAVDB_URL_PATTERN = r"(https://javdb\.com/v/[0-9A-Za-z]+)"
JAVDB_ACTOR_PATTERN = r"(https://javdb\.com/actors/[0-9A-Za-z\-]+)"
MAGNET_LINK_PATTERN = r"(magnet:\?[^\s\n]+)"  # Improved pattern to capture full magnet links


class MainForm(QMainWindow, Ui_MainWindow):
    """Main application window for JAV database URL management."""

    def __init__(self) -> None:
        """Initialize the main application window and database."""
        super(MainForm, self).__init__()
        
        self.setupUi(self)
        self.setWindowTitle('JAV Clipboard Manager')
        
        # Database file path: always in the same directory as the program file
        # This ensures the database is found regardless of where the program is executed from
        self.fn: Path = Path(__file__).parent / 'copy_2_aj.db'
        self.albums: List[str] = []
        self.actors: List[str] = []
        
        # Pause state: when True, new clipboard content is not saved
        self._paused: bool = False
        
        # Load existing database
        self.read_db()
        self.check_db()
        
        # Clipboard monitoring setup
        self._count_timer = QTimer(self)
        self._count_timer.timeout.connect(self.count_down)
        self._count_timer.start(500)  # Monitor every 500ms
        self.pre_clip: str = 'init'
        self.cur_clip: str = 'init'
        self.pre_export_clip: str = ''
        
        # Connect UI buttons to methods
        self.pushButton.clicked.connect(self.export)
        self.pushButton_2.clicked.connect(self.remove_pre)
        self.pushButton_3.clicked.connect(self.copy_pre)
        self.pushButton_4.clicked.connect(self.save_db)
        self.radioButton_2.clicked.connect(self.copyinit)
        self.radioButton_1.clicked.connect(self.copyinit)
        
        # Add pause button dynamically
        self._add_pause_button()
        
        logger.info("Application initialized successfully")

    def _add_pause_button(self) -> None:
        """Add a pause button to toggle clipboard monitoring."""
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QRect
        
        self.pushButton_pause = QPushButton(self.centralwidget)
        self.pushButton_pause.setGeometry(QRect(530, 450, 75, 41))
        self.pushButton_pause.setText("Pause")
        self.pushButton_pause.clicked.connect(self._toggle_pause)
        self.pushButton_pause.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        
    def _toggle_pause(self) -> None:
        """Toggle pause state for clipboard monitoring."""
        self._paused = not self._paused
        if self._paused:
            self.pushButton_pause.setText("Resuming...")
            self.pushButton_pause.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
            logger.info("Clipboard monitoring paused")
        else:
            self.pushButton_pause.setText("Pause")
            self.pushButton_pause.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            logger.info("Clipboard monitoring resumed")

    def copyinit(self) -> None:
        """Reset clipboard to 'init' marker."""
        try:
            pyperclip.copy('init')
        except Exception as e:
            logger.error(f"Failed to copy 'init' to clipboard: {e}")

    def copy_pre(self) -> None:
        """Copy the previous export command to clipboard."""
        try:
            self.radioButton_1.setChecked(True)
            pyperclip.copy(self.pre_export_clip)
            logger.info("Previous export copied to clipboard")
        except Exception as e:
            logger.error(f"Failed to copy previous export: {e}")
            self.show_error("Copy Error", f"Failed to copy to clipboard: {e}")

    def remove_pre(self) -> None:
        """Remove items from the previous export from the database."""
        try:
            # Extract URLs and links from previous export
            ts = re.findall(JAVDB_URL_PATTERN, self.pre_export_clip)
            ss = re.findall(JAVDB_ACTOR_PATTERN, self.pre_export_clip)
            ms = re.findall(MAGNET_LINK_PATTERN, self.pre_export_clip)
            
            # Remove album URLs
            for f in ts:
                if f in self.albums:
                    self.albums.remove(f)
            
            # Remove magnet links
            for f in ms:
                if f in self.albums:
                    self.albums.remove(f)

            # Remove actor URLs
            for f in ss:
                if f in self.actors:
                    self.actors.remove(f)
            
            self.check_db()
            self.save_db()
            logger.info(f"Removed {len(ts)} albums, {len(ms)} magnets, {len(ss)} actors from database")
        except Exception as e:
            logger.error(f"Error removing previous exports: {e}")
            self.show_error("Remove Error", f"Failed to remove items: {e}")

    def _validate_limit(self, text: str, field_name: str) -> int:
        """Validate and return integer limit value.
        
        Args:
            text: The text input to validate
            field_name: Name of the field for error messages
            
        Returns:
            Valid integer limit, defaults to 9999 if invalid
        """
        try:
            limit = int(text)
            if limit <= 0:
                raise ValueError("Limit must be positive")
            return limit
        except (ValueError, TypeError):
            logger.warning(f"Invalid input for {field_name}: '{text}'. Using default limit 9999")
            self.show_warning("Input Error", f"Invalid limit in {field_name}. Using default (9999)")
            return 9999

    def export(self) -> None:
        """Export albums and/or actors as command sequences to clipboard with DOS-compatible CRLF line breaks."""
        try:
            cmd_lines = []
            
            # Export albums if requested
            if self.radioButton_5.isChecked() or self.radioButton_3.isChecked():
                c = 0
                limit = self._validate_limit(self.lineEdit_1.text(), "Album Limit")
                for f in self.albums:
                    cmd_lines.append(f)
                    c += 1
                    if c >= limit:
                        break
                cmd_lines.append('q')
                cmd_lines.append('')
            
            # Export actors if requested
            if self.radioButton_5.isChecked() or self.radioButton_4.isChecked():
                c = 0
                limit = self._validate_limit(self.lineEdit_2.text(), "Actor Limit")
                cmd_option = ''
                
                # Build command options from checkboxes
                if self.checkBox_1.isChecked():
                    cmd_option = cmd_option + '-nl '
                if self.checkBox_2.isChecked():
                    cmd_option = cmd_option + '-nc '
                if self.checkBox_3.isChecked():
                    cmd_option = cmd_option + '-fda '
                if self.checkBox_4.isChecked():
                    cmd_option = cmd_option + '-fdm '
                if self.checkBox_5.isChecked():
                    cmd_option = cmd_option + '-fdo '
                
                for f in self.actors:
                    cmd_lines.append('fjl ' + cmd_option + '-il ' + f)
                    c += 1
                    if c >= limit:
                        break
            
            # Join with CRLF (\r\n) for DOS/CMD compatibility
            # This ensures each command appears on its own line when pasted in DOS
            cmd_txt = '\r\n'.join(cmd_lines)
            
            # Copy to clipboard with DOS-compatible line breaks
            pyperclip.copy(cmd_txt)
            self.pre_export_clip = cmd_txt
            logger.info(f"Exported with CRLF line breaks for DOS compatibility")
        except Exception as e:
            logger.error(f"Error during export: {e}")
            self.show_error("Export Error", f"Failed to export: {e}")

    def show_error(self, title: str, message: str) -> None:
        """Display error message dialog."""
        QMessageBox.critical(self, title, message)

    def show_warning(self, title: str, message: str) -> None:
        """Display warning message dialog."""
        QMessageBox.warning(self, title, message)

    def save_db(self) -> None:
        """Save albums and actors to database file with UTF-8 encoding and DOS-compatible CRLF line breaks."""
        try:
            db_lines = []
            for f in self.albums:
                db_lines.append(f)
            for f in self.actors:
                db_lines.append(f)
            # Use CRLF (\r\n) for DOS/CMD compatibility
            with open(self.fn, 'w', encoding='utf-8') as fp:
                fp.write('\r\n'.join(db_lines))
            logger.info(f"Database saved: {len(self.albums)} albums, {len(self.actors)} actors")
        except IOError as e:
            logger.error(f"Failed to save database to {self.fn}: {e}")
            self.show_error("Save Error", f"Failed to save database: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while saving database: {e}")
            self.show_error("Save Error", f"Unexpected error: {e}")

    def count_down(self) -> None:
        """Monitor clipboard for new URLs and links (called every 500ms)."""
        try:
            self.cur_clip = pyperclip.paste()
        except Exception as e:
            logger.warning(f"Failed to read clipboard: {e}")
            return
        
        # Check if clipboard content changed
        if self.pre_clip != self.cur_clip:
            self.pre_clip = self.cur_clip
            
            # Skip processing if paused
            if self._paused:
                logger.debug("Clipboard monitoring paused, skipped new content")
                return
            
            # Extract URLs and links from clipboard
            ts = re.findall(JAVDB_URL_PATTERN, self.cur_clip)
            ss = re.findall(JAVDB_ACTOR_PATTERN, self.cur_clip)
            ms = re.findall(MAGNET_LINK_PATTERN, self.cur_clip)
            
            # Add or remove based on current mode
            if self.radioButton_1.isChecked():
                # Add mode
                self.albums = self.albums + ts   
                self.albums = self.albums + ms
                self.actors = self.actors + ss
                if ts or ms or ss:
                    logger.info(f"Added from clipboard: {len(ts)} albums, {len(ms)} magnets, {len(ss)} actors")
            else:
                # Remove mode
                for f in ts:
                    if f in self.albums:
                        self.albums.remove(f)
                for f in ms:
                    if f in self.albums:
                        self.albums.remove(f)                        
                for f in ss:
                    if f in self.actors:
                        self.actors.remove(f)
                if ts or ms or ss:
                    logger.info(f"Removed from database: {len(ts)} albums, {len(ms)} magnets, {len(ss)} actors")
            
            self.check_db()

    def read_db(self) -> None:
        """Load albums and actors from database file."""
        try:
            if self.fn.is_file():
                with open(self.fn, 'r', encoding='utf-8') as fp:
                    txt = fp.read()
                self.albums = re.findall(JAVDB_URL_PATTERN, txt)       
                self.actors = re.findall(JAVDB_ACTOR_PATTERN, txt)
                logger.info(f"Database loaded: {len(self.albums)} albums, {len(self.actors)} actors")
            else:
                self.albums = []
                self.actors = []
                logger.info("No database file found, starting with empty lists")
        except IOError as e:
            logger.error(f"Failed to read database from {self.fn}: {e}")
            self.albums = []
            self.actors = []
        except Exception as e:
            logger.error(f"Unexpected error while reading database: {e}")
            self.albums = []
            self.actors = []

    def check_db(self) -> None:
        """Deduplicate lists and update UI labels."""
        try:
            self.albums = list(set(self.albums))
            self.actors = list(set(self.actors))
            self.label_1.setText(str(len(self.albums)))
            self.label_3.setText(str(len(self.actors)))
        except Exception as e:
            logger.error(f"Error updating database: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainForm()
    win.show()
    sys.exit(app.exec())