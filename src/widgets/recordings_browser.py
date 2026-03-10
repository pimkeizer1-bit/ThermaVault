"""Global recordings browser: filter and sort all recordings across all panels."""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ..models import PanelData
from ..theme import current_theme, ThemeManager
from .recording_table import REPAIR_COLORS, REPAIR_COLORS_LIGHT, REPAIR_DISPLAY_NAMES

FILTER_TYPES = [
    ('initial',    'Initial'),
    ('pre_repair', 'Pre Repair'),
    ('post_repair','Post Repair'),
    ('check',      'Check'),
    ('internal',   'Internal'),
    ('unknown',    'Unknown'),
]

COLUMNS = ['Panel', 'Date', 'Type', 'Repair #', 'Frames', 'Has Report', 'Recording ID']


class RecordingsBrowserWidget(QWidget):
    """Shows all recordings across all panels with type filter checkboxes."""

    # Emits (panel_id, recording_id) when user double-clicks a row
    recording_selected = pyqtSignal(str, str)
    # Emits list of (panel_id, recording_id) tuples to start triage mode
    triage_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels: list[PanelData] = []
        self._reports: dict[str, list] = {}   # panel_id -> list[ReportFile]
        self._rows: list[tuple] = []           # (panel_id, recording_id) per row
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self.apply_theme)

    def _init_ui(self):
        t = current_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Filter bar
        filter_frame = QFrame()
        filter_frame.setStyleSheet(
            f"QFrame {{ background-color: {t.surface_bg}; border: 1px solid {t.border}; "
            f"border-radius: 4px; padding: 4px; }}"
        )
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 4, 8, 4)
        filter_layout.setSpacing(12)

        filter_layout.addWidget(QLabel("Show:"))

        self._filter_cbs: dict[str, QCheckBox] = {}
        for rt, label in FILTER_TYPES:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.toggled.connect(self._refresh_table)
            filter_layout.addWidget(cb)
            self._filter_cbs[rt] = cb

        filter_layout.addStretch()

        all_btn = QPushButton("All")
        all_btn.setFixedWidth(45)
        all_btn.clicked.connect(lambda: self._set_all_filters(True))
        filter_layout.addWidget(all_btn)

        none_btn = QPushButton("None")
        none_btn.setFixedWidth(50)
        none_btn.clicked.connect(lambda: self._set_all_filters(False))
        filter_layout.addWidget(none_btn)

        filter_layout.addSpacing(16)

        triage_btn = QPushButton("⚡ Triage Unclassified")
        triage_btn.setToolTip("Step through all Unknown recordings and classify or hide them one by one")
        triage_btn.clicked.connect(self._start_triage)
        filter_layout.addWidget(triage_btn)

        layout.addWidget(filter_frame)

        # Count label
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(self.count_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        # Hint
        hint = QLabel("Double-click a recording to open it in the panel view")
        hint.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        layout.addWidget(hint)

    def set_data(self, panels: list[PanelData], reports_by_panel: dict):
        """Load all panel data and their reports."""
        self._panels = panels
        self._reports = reports_by_panel
        self._refresh_table()

    def clear(self):
        self._panels = []
        self._reports = {}
        self._rows = []
        self.table.setRowCount(0)
        self.count_label.setText("")

    def _set_all_filters(self, checked: bool):
        for cb in self._filter_cbs.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._refresh_table()

    def _refresh_table(self):
        active_types = {rt for rt, cb in self._filter_cbs.items() if cb.isChecked()}

        # Also match old aliases
        alias_map = {'baseline': 'initial', 'followup': 'check'}

        is_dark = ThemeManager.instance().is_dark
        colors = REPAIR_COLORS if is_dark else REPAIR_COLORS_LIGHT

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._rows = []

        for panel in self._panels:
            panel_reports = self._reports.get(panel.panel_id, [])

            for rec in panel.recordings:
                rt = rec.repair_type or 'unknown'
                canonical = alias_map.get(rt, rt)
                if canonical not in active_types and rt not in active_types:
                    continue

                row = self.table.rowCount()
                self.table.insertRow(row)
                self._rows.append((panel.panel_id, rec.recording_id))

                display_type = REPAIR_DISPLAY_NAMES.get(rt, rt.replace('_', ' ').title())
                bg_hex = colors.get(rt) or colors.get(canonical)

                try:
                    dt = datetime.fromisoformat(rec.timestamp)
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                    sort_key = dt.strftime("%Y%m%d%H%M%S")
                except (ValueError, TypeError):
                    date_str = rec.timestamp or '-'
                    sort_key = ''

                has_report = self._has_report(rec, panel_reports)

                values = [
                    panel.name,
                    date_str,
                    display_type,
                    str(rec.repair_number) if rec.repair_number is not None else '-',
                    str(rec.frame_count),
                    'Yes' if has_report else '-',
                    rec.recording_id,
                ]

                for col, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    # Store sortable value for date column
                    if col == 1:
                        item.setData(Qt.ItemDataRole.UserRole, sort_key)
                    if bg_hex:
                        item.setBackground(QColor(bg_hex))
                    if col == 5 and has_report:
                        item.setForeground(QColor('#47d4a0'))
                    self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        total = self.table.rowCount()
        self.count_label.setText(f"{total} recording(s)")

    def _has_report(self, rec, reports) -> bool:
        for report in reports:
            try:
                dt = datetime.fromisoformat(rec.timestamp)
                if dt.strftime('%Y%m%d_%H%M%S') in report.filename:
                    return True
            except (ValueError, TypeError):
                pass
            if rec.recording_id in report.filename:
                return True
        return False

    def _on_double_click(self, index):
        row = index.row()
        if 0 <= row < len(self._rows):
            panel_id, recording_id = self._rows[row]
            self.recording_selected.emit(panel_id, recording_id)

    def _start_triage(self):
        """Collect all unknown recordings and emit triage_requested."""
        alias_map = {'baseline': 'initial', 'followup': 'check'}
        unknown_types = {'unknown', ''}

        queue = []
        for panel in self._panels:
            for rec in panel.recordings:
                rt = rec.repair_type or ''
                canonical = alias_map.get(rt, rt)
                if rt in unknown_types or canonical in unknown_types:
                    queue.append((panel.panel_id, rec.recording_id))

        if not queue:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "All Classified",
                                    "There are no unclassified recordings.")
            return

        self.triage_requested.emit(queue)

    def apply_theme(self):
        t = current_theme()
        self.count_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        if self._panels:
            self._refresh_table()
