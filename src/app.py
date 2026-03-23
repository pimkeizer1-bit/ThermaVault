"""ThermaVault main window."""

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QApplication,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox,
    QPushButton, QFormLayout, QFrame, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from .data_loader import DataLoader
from .data_writer import DataWriter
from .annotations import AnnotationManager
from .settings import AppSettings
from .theme import ThemeManager, current_theme
from .widgets.panel_list import PanelListWidget
from .widgets.panel_detail import PanelDetailWidget
from .widgets.recordings_browser import RecordingsBrowserWidget
from .widgets.qr_display import QRBatchPrintDialog


class TempRangeDialog(QDialog):
    """Dialog for setting the global temperature range."""

    def __init__(self, temp_min: float, temp_max: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Temperature Range")
        self.setFixedSize(300, 150)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-40.0, 500.0)
        self.min_spin.setSuffix(" °C")
        self.min_spin.setDecimals(1)
        self.min_spin.setValue(temp_min)
        form.addRow("Min Temperature:", self.min_spin)

        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-40.0, 500.0)
        self.max_spin.setSuffix(" °C")
        self.max_spin.setDecimals(1)
        self.max_spin.setValue(temp_max)
        form.addRow("Max Temperature:", self.max_spin)

        layout.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch()

        reset_btn = QPushButton("Reset Default")
        reset_btn.clicked.connect(self._reset_defaults)
        buttons.addWidget(reset_btn)

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        buttons.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        layout.addLayout(buttons)

    def _reset_defaults(self):
        self.min_spin.setValue(10.0)
        self.max_spin.setValue(130.0)

    def get_range(self) -> tuple[float, float]:
        return self.min_spin.value(), self.max_spin.value()


class MainWindow(QMainWindow):
    """ThermaVault main application window."""

    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.data_loader = None

        self.setWindowTitle("ThermaVault - Thermal Panel Viewer")
        self.resize(1200, 700)

        self._init_menu()
        self._init_ui()
        self._apply_stylesheet()
        self._restore_state()

        # Connect theme changes
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        # Pass settings to child widgets
        self.panel_detail.set_settings(self.settings)

        # Apply saved temperature range to playback widget
        self.panel_detail.set_temp_range(
            self.settings.temp_range_min,
            self.settings.temp_range_max
        )

        # Auto-load last folder
        last_folder = self.settings.last_data_folder
        if last_folder:
            self._load_data(last_folder)

    def _init_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open Folder...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_folder)
        file_menu.addAction(open_action)

        # Recent folders submenu
        self.recent_menu = file_menu.addMenu("&Recent Folders")
        self._update_recent_menu()

        file_menu.addSeparator()

        refresh_action = QAction("&Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh)
        file_menu.addAction(refresh_action)

        import_action = QAction("&Import recordings from folder...", self)
        import_action.triggered.connect(self._import_from_folder)
        file_menu.addAction(import_action)

        print_qr_action = QAction("Print QR Labels...", self)
        print_qr_action.setToolTip("Print QR labels for multiple panels at once")
        print_qr_action.triggered.connect(self._open_qr_batch_print)
        file_menu.addAction(print_qr_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        temp_range_action = QAction("&Temperature Range...", self)
        temp_range_action.setShortcut("Ctrl+R")
        temp_range_action.triggered.connect(self._show_temp_range_dialog)
        view_menu.addAction(temp_range_action)

        view_menu.addSeparator()

        self.theme_action = QAction("Switch to &Light Theme", self)
        self.theme_action.setShortcut("Ctrl+T")
        self.theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self.theme_action)
        self._update_theme_action_text()

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _init_ui(self):
        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: panel list
        self.panel_list = PanelListWidget()
        self.panel_list.setMinimumWidth(250)
        self.panel_list.setMaximumWidth(400)
        self.panel_list.open_btn.clicked.connect(self._open_folder)
        self.panel_list.panel_selected.connect(self._on_panel_selected)
        self.splitter.addWidget(self.panel_list)

        # Right side: triage banner + tab widget
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Triage banner (hidden until triage mode starts)
        self.triage_bar = QFrame()
        self.triage_bar.setStyleSheet(
            "QFrame { background-color: #1a3a5c; border-bottom: 2px solid #2d7dd2; padding: 4px; }"
        )
        triage_layout = QHBoxLayout(self.triage_bar)
        triage_layout.setContentsMargins(10, 6, 10, 6)
        triage_layout.setSpacing(8)

        self.triage_progress_label = QLabel("")
        self.triage_progress_label.setStyleSheet("color: #a0c4e8; font-size: 11px; min-width: 60px;")
        triage_layout.addWidget(self.triage_progress_label)

        self.triage_info_label = QLabel("")
        self.triage_info_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        triage_layout.addWidget(self.triage_info_label, 1)

        triage_layout.addWidget(QLabel("→"))

        REPAIR_LABELS = [
            ('initial', 'Initial'), ('pre_repair', 'Pre Repair'),
            ('post_repair', 'Post Repair'), ('check', 'Check'), ('internal', 'Internal'),
        ]
        self._triage_classify_btns = {}
        for rt, label in REPAIR_LABELS:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "QPushButton { background-color: #2d5a8e; color: white; border: 1px solid #4a8abf; "
                "border-radius: 3px; padding: 0 8px; } "
                "QPushButton:hover { background-color: #3a7abf; }"
            )
            btn.clicked.connect(lambda checked, r=rt: self._triage_classify(r))
            triage_layout.addWidget(btn)
            self._triage_classify_btns[rt] = btn

        hide_btn = QPushButton("Hide")
        hide_btn.setFixedHeight(28)
        hide_btn.setStyleSheet(
            "QPushButton { background-color: #5c2020; color: #ffaaaa; border: 1px solid #a03030; "
            "border-radius: 3px; padding: 0 8px; } "
            "QPushButton:hover { background-color: #7a2020; }"
        )
        hide_btn.clicked.connect(self._triage_hide)
        triage_layout.addWidget(hide_btn)

        skip_btn = QPushButton("Skip →")
        skip_btn.setFixedHeight(28)
        skip_btn.setStyleSheet(
            "QPushButton { background-color: #3a3a3a; color: #cccccc; border: 1px solid #555; "
            "border-radius: 3px; padding: 0 8px; } "
            "QPushButton:hover { background-color: #4a4a4a; }"
        )
        skip_btn.clicked.connect(self._triage_skip)
        triage_layout.addWidget(skip_btn)

        done_btn = QPushButton("✕ Done")
        done_btn.setFixedHeight(28)
        done_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #a0a0a0; border: none; padding: 0 4px; } "
            "QPushButton:hover { color: white; }"
        )
        done_btn.clicked.connect(self._triage_stop)
        triage_layout.addWidget(done_btn)

        self.triage_bar.hide()
        right_layout.addWidget(self.triage_bar)

        # Tab widget with panel detail + recordings browser
        self.right_tabs = QTabWidget()
        self.right_tabs.setDocumentMode(True)

        self.panel_detail = PanelDetailWidget()
        self.right_tabs.addTab(self.panel_detail, "Panel")

        self.recordings_browser = RecordingsBrowserWidget()
        self.recordings_browser.recording_selected.connect(self._on_browser_recording_selected)
        self.recordings_browser.triage_requested.connect(self._triage_start)
        self.right_tabs.addTab(self.recordings_browser, "All Recordings")

        right_layout.addWidget(self.right_tabs, 1)
        self.splitter.addWidget(right_widget)

        # Triage state
        self._triage_queue: list[tuple[str, str]] = []  # [(panel_id, recording_id)]
        self._triage_index: int = 0

        # Set initial splitter sizes
        self.splitter.setSizes([280, 920])

        self.setCentralWidget(self.splitter)

        # Status bar
        self.statusBar().showMessage("Ready - Open a ThermalPanel data folder to begin")

    def _apply_stylesheet(self):
        """Build and apply the main stylesheet from current theme."""
        t = current_theme()
        qss = f"""
            QMainWindow, QWidget {{
                background-color: {t.window_bg};
                color: {t.text_primary};
            }}
            QMenuBar {{
                background-color: {t.widget_bg};
                color: {t.text_primary};
                border-bottom: 1px solid {t.border};
            }}
            QMenuBar::item:selected {{
                background-color: {t.button_hover};
            }}
            QMenu {{
                background-color: {t.widget_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
            }}
            QMenu::item:selected {{
                background-color: {t.button_hover};
            }}
            QLineEdit {{
                background-color: {t.surface_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{
                border-color: {t.accent_blue};
            }}
            QPushButton {{
                background-color: {t.button_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {t.button_hover};
                border-color: {t.border_hover};
            }}
            QPushButton:pressed {{
                background-color: {t.button_pressed};
            }}
            QListWidget {{
                background-color: {t.surface_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 12px;
                border-bottom: 1px solid {t.border};
            }}
            QListWidget::item:selected {{
                background-color: {t.accent_blue};
                color: white;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {t.button_hover};
            }}
            QTabWidget::pane {{
                border: 1px solid {t.border};
                background-color: {t.widget_bg};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: {t.surface_bg};
                color: {t.text_secondary};
                border: 1px solid {t.border};
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {t.widget_bg};
                color: {t.text_primary};
                border-bottom-color: {t.widget_bg};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {t.button_hover};
            }}
            QTableWidget {{
                background-color: {t.surface_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                gridline-color: {t.border};
                selection-background-color: {t.accent_blue};
            }}
            QTableWidget::item {{
                padding: 4px 8px;
            }}
            QHeaderView::section {{
                background-color: {t.widget_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                padding: 6px 8px;
                font-weight: bold;
            }}
            QScrollBar:vertical {{
                background-color: {t.scrollbar_bg};
                width: 10px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {t.scrollbar_handle};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {t.scrollbar_handle_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: {t.scrollbar_bg};
                height: 10px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {t.scrollbar_handle};
                border-radius: 5px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {t.scrollbar_handle_hover};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QSplitter::handle {{
                background-color: {t.border};
                width: 2px;
            }}
            QStatusBar {{
                background-color: {t.widget_bg};
                color: {t.text_secondary};
                border-top: 1px solid {t.border};
            }}
            QFrame {{
                border: none;
            }}
            QTextEdit {{
                background-color: {t.surface_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
            QDoubleSpinBox, QSpinBox {{
                background-color: {t.surface_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QDoubleSpinBox:focus, QSpinBox:focus {{
                border-color: {t.accent_blue};
            }}
            QComboBox {{
                background-color: {t.surface_bg};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QComboBox:hover {{
                border-color: {t.border_hover};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QCheckBox {{
                color: {t.text_primary};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 2px solid {t.border_hover};
                border-radius: 3px;
                background-color: {t.surface_bg};
            }}
            QCheckBox::indicator:hover {{
                border-color: {t.accent_blue};
            }}
            QCheckBox::indicator:checked {{
                background-color: {t.accent_blue};
                border-color: {t.accent_blue};
            }}
            QSlider::groove:horizontal {{
                background: {t.surface_bg};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {t.accent_blue};
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
        """
        self.setStyleSheet(qss)

    def _open_folder(self):
        """Open a folder browser dialog."""
        start_dir = self.settings.last_data_folder or ""
        folder = QFileDialog.getExistingDirectory(
            self, "Select ThermalPanel Data Folder", start_dir
        )
        if folder:
            self._load_data(folder)

    def _load_data(self, root_path: str):
        """Load data from the given root path."""
        self.data_loader = DataLoader(root_path)
        success, msg = self.data_loader.load_all()

        if not success:
            QMessageBox.warning(
                self, "Load Error",
                f"Could not load data from:\n{root_path}\n\n{msg}"
            )
            self.statusBar().showMessage(f"Error: {msg}")
            return

        # Save to settings
        self.settings.last_data_folder = root_path
        self.settings.add_recent_folder(root_path)
        self._update_recent_menu()

        # Set QR directory for auto-generation
        from pathlib import Path
        qr_dir = str(Path(root_path) / "QR codes")
        self.panel_detail.set_qr_dir(qr_dir)

        # Set up annotation manager for field notes
        self._annotation_manager = AnnotationManager(root_path)
        self.panel_detail.set_annotation_manager(self._annotation_manager)

        # Set up data writer for data manager
        self._data_writer = DataWriter(root_path)
        self.panel_detail.set_data_writer(self._data_writer)
        self.panel_detail.data_manager_tab.data_changed.connect(
            self._refresh_preserving_selection
        )
        self.panel_detail.playback_tab.reclassified.connect(
            self._refresh_preserving_selection
        )

        # Populate panel list
        panels = self.data_loader.get_all_panels()
        self.panel_list.set_panels(panels)
        self.panel_list.set_path(root_path)

        # Populate recordings browser
        reports_by_panel = {
            p.panel_id: self.data_loader.get_reports(p.panel_id)
            for p in panels
        }
        self.recordings_browser.set_data(panels, reports_by_panel)

        # Clear detail view
        self.panel_detail.clear()

        self.statusBar().showMessage(msg)

    def _on_panel_selected(self, panel_id: str):
        """Handle panel selection from the list."""
        if self.data_loader is None:
            return

        panel = self.data_loader.get_panel(panel_id)
        if panel is None:
            return

        reports = self.data_loader.get_reports(panel_id)
        repair_events = self.data_loader.get_repair_history(panel_id)
        qr_path = self.data_loader.get_qr_path(panel_id)

        all_panels = list(self.data_loader.panels.values())
        self.panel_detail.set_panel(panel, reports, repair_events, qr_path,
                                    all_panels=all_panels)
        self.statusBar().showMessage(
            f"Panel: {panel.name}  |  {len(panel.recordings)} recordings  |  "
            f"{len([r for r in reports if r.is_pdf])} reports"
        )

    def _on_browser_recording_selected(self, panel_id: str, recording_id: str):
        """Navigate to a panel+recording when double-clicked in the recordings browser."""
        # Switch to Panel tab
        self.right_tabs.setCurrentIndex(0)

        # Select the panel in the list
        for i in range(self.panel_list.list_widget.count()):
            item = self.panel_list.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == panel_id:
                self.panel_list.list_widget.setCurrentItem(item)
                break

        # Switch to Playback tab and select the recording
        playback_tab_index = self.panel_detail.tabs.indexOf(self.panel_detail.playback_tab)
        self.panel_detail.tabs.setCurrentIndex(playback_tab_index)
        self.panel_detail.playback_tab.select_recording_by_id(recording_id)

    # -- Triage mode --

    def _triage_start(self, queue: list):
        """Begin triage mode with a list of (panel_id, recording_id) tuples."""
        self._triage_queue = queue
        self._triage_index = 0
        if not queue:
            return
        self.triage_bar.show()
        self.right_tabs.setCurrentIndex(0)
        self._triage_show_current()

    def _triage_show_current(self):
        if self._triage_index >= len(self._triage_queue):
            self._triage_stop(finished=True)
            return

        panel_id, recording_id = self._triage_queue[self._triage_index]
        total = len(self._triage_queue)
        self.triage_progress_label.setText(
            f"{self._triage_index + 1} / {total}"
        )

        # Look up panel name and recording date
        panel = self.data_loader.get_panel(panel_id) if self.data_loader else None
        panel_name = panel.name if panel else panel_id
        rec_date = ""
        if panel:
            for r in panel.recordings:
                if r.recording_id == recording_id:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(r.timestamp)
                        rec_date = dt.strftime("  %Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        pass
                    break
        self.triage_info_label.setText(f"{panel_name}{rec_date}")

        # Navigate to the recording
        self._on_browser_recording_selected(panel_id, recording_id)

    def _triage_classify(self, repair_type: str):
        if self._triage_index >= len(self._triage_queue):
            return
        panel_id, recording_id = self._triage_queue[self._triage_index]
        if self._data_writer:
            self._data_writer.reclassify_recording(panel_id, recording_id, repair_type)
        self._triage_advance()

    def _triage_hide(self):
        if self._triage_index >= len(self._triage_queue):
            return
        panel_id, recording_id = self._triage_queue[self._triage_index]
        if self._data_writer:
            self._data_writer.delete_recordings(panel_id, [recording_id], delete_files=False)
        self._triage_advance()

    def _triage_skip(self):
        self._triage_advance()

    def _triage_advance(self):
        self._triage_index += 1
        if self._triage_index >= len(self._triage_queue):
            self._triage_stop(finished=True)
        else:
            self._triage_show_current()

    def _triage_stop(self, finished: bool = False):
        self.triage_bar.hide()
        self._refresh_preserving_selection()
        if finished and self._triage_queue:
            self.statusBar().showMessage(
                f"Triage complete — {len(self._triage_queue)} recording(s) reviewed"
            )

    def _refresh(self):
        """Reload data from the current folder."""
        if self.settings.last_data_folder:
            self._load_data(self.settings.last_data_folder)

    def _refresh_preserving_selection(self):
        """Reload data but re-select the current panel and tab."""
        if not self.settings.last_data_folder:
            return

        # Remember current panel and tab
        current_item = self.panel_list.list_widget.currentItem()
        current_panel_id = None
        if current_item:
            current_panel_id = current_item.data(Qt.ItemDataRole.UserRole)
        current_tab = self.panel_detail.tabs.currentIndex()

        self._load_data(self.settings.last_data_folder)

        # Re-select panel
        if current_panel_id:
            for i in range(self.panel_list.list_widget.count()):
                item = self.panel_list.list_widget.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == current_panel_id:
                    self.panel_list.list_widget.setCurrentItem(item)
                    break

        # Restore tab
        if current_tab >= 0:
            self.panel_detail.tabs.setCurrentIndex(current_tab)

    def _open_qr_batch_print(self):
        """Open batch QR print dialog for all loaded panels."""
        if not hasattr(self, 'data_loader') or not self.data_loader:
            QMessageBox.information(self, "No Data", "Open a data folder first.")
            return
        panels = list(self.data_loader.panels.values())
        if not panels:
            QMessageBox.information(self, "No Panels", "No panels loaded.")
            return
        qr_dir = getattr(self.panel_detail, '_qr_dir', None)
        dlg = QRBatchPrintDialog(panels, qr_dir, parent=self)
        dlg.exec()

    def _import_from_folder(self):
        """Import new recordings from another ThermalPanel data folder."""
        if not self.settings.last_data_folder:
            QMessageBox.warning(self, "No Data Loaded",
                                "Please open a data folder first before importing.")
            return

        if not hasattr(self, '_data_writer') or not self._data_writer:
            QMessageBox.warning(self, "No Data Loaded",
                                "Please open a data folder first before importing.")
            return

        folder = QFileDialog.getExistingDirectory(
            self, "Select source folder to import from",
            "", QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return

        # Confirm
        reply = QMessageBox.question(
            self, "Import Recordings",
            f"Import new recordings from:\n{folder}\n\n"
            f"Into current database:\n{self.settings.last_data_folder}\n\n"
            "This will copy new recording folders and add them to your database. "
            "Your existing cleanup (repair types, hidden recordings) will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok, msg = self._data_writer.import_from_folder(folder, copy_files=True)

        if ok:
            QMessageBox.information(self, "Import Complete", msg)
            self._refresh_preserving_selection()
        else:
            QMessageBox.warning(self, "Import Failed", msg)

    def _toggle_theme(self):
        ThemeManager.instance().toggle()

    def _show_temp_range_dialog(self):
        """Show dialog to set the global playback temperature range."""
        dlg = TempRangeDialog(
            self.settings.temp_range_min,
            self.settings.temp_range_max,
            parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            temp_min, temp_max = dlg.get_range()
            if temp_min >= temp_max:
                QMessageBox.warning(
                    self, "Invalid Range",
                    "Min temperature must be less than max temperature."
                )
                return
            self.settings.temp_range_min = temp_min
            self.settings.temp_range_max = temp_max
            self.panel_detail.set_temp_range(temp_min, temp_max)
            self.statusBar().showMessage(
                f"Temperature range set to {temp_min:.0f} - {temp_max:.0f} °C"
            )

    def _on_theme_changed(self):
        self._apply_stylesheet()
        self._update_theme_action_text()
        self.panel_list.apply_theme()
        self.panel_detail.apply_theme()

    def _update_theme_action_text(self):
        if ThemeManager.instance().is_dark:
            self.theme_action.setText("Switch to &Light Theme")
        else:
            self.theme_action.setText("Switch to &Dark Theme")

    def _update_recent_menu(self):
        self.recent_menu.clear()
        recent = self.settings.recent_folders
        if not recent:
            action = self.recent_menu.addAction("(no recent folders)")
            action.setEnabled(False)
        else:
            for folder in recent:
                action = self.recent_menu.addAction(folder)
                action.triggered.connect(lambda checked, f=folder: self._load_data(f))

    def _show_about(self):
        QMessageBox.about(
            self, "About ThermaVault",
            "<h2>ThermaVault</h2>"
            "<p>Thermal Panel Data Viewer</p>"
            "<p>A standalone tool for browsing and managing ThermalPanel data, "
            "recordings, reports, and repair history.</p>"
        )

    def _restore_state(self):
        """Restore window geometry and splitter state."""
        geom = self.settings.window_geometry
        if geom and not geom.isEmpty():
            self.restoreGeometry(geom)
        splitter_state = self.settings.splitter_state
        if splitter_state and not splitter_state.isEmpty():
            self.splitter.restoreState(splitter_state)

    def closeEvent(self, event):
        """Save window state before closing."""
        self.settings.window_geometry = self.saveGeometry()
        self.settings.splitter_state = self.splitter.saveState()
        super().closeEvent(event)
