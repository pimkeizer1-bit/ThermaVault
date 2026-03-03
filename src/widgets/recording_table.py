"""Recordings tab: sortable table of recording entries."""

from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ..models import RecordingData
from ..theme import current_theme


# Repair type display colors (used for cell background tinting)
# Includes old names (baseline, followup) as aliases for backwards compat
REPAIR_COLORS = {
    'initial': '#2a4a2a',
    'baseline': '#2a4a2a',
    'pre_repair': '#4a3a1a',
    'post_repair': '#1a2a4a',
    'check': '#3a3a3a',
    'followup': '#3a3a3a',
    'internal': '#3a2a4a',
}

REPAIR_COLORS_LIGHT = {
    'initial': '#d4edda',
    'baseline': '#d4edda',
    'pre_repair': '#fff3cd',
    'post_repair': '#cce5ff',
    'check': '#e2e3e5',
    'followup': '#e2e3e5',
    'internal': '#e8daef',
}

# Map old names to new display names
REPAIR_DISPLAY_NAMES = {
    'initial': 'Initial',
    'baseline': 'Initial',
    'pre_repair': 'Pre Repair',
    'post_repair': 'Post Repair',
    'check': 'Check',
    'followup': 'Check',
    'internal': 'Internal',
    'unknown': 'Unknown',
}

COLUMNS = ['Date', 'Type', 'Repair #', 'Duration', 'Frames', 'Min °C', 'Max °C', 'Avg °C', 'Notes']


class RecordingTableWidget(QWidget):
    """Sortable table showing panel recordings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("No recordings for this panel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {current_theme().text_muted}; padding: 40px;")
        layout.addWidget(self.empty_label)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def set_recordings(self, recordings: list[RecordingData]):
        """Populate the table with recording data."""
        if not recordings:
            self.empty_label.show()
            self.table.hide()
            return

        self.empty_label.hide()
        self.table.show()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(recordings))

        for row, rec in enumerate(recordings):
            # Date
            try:
                dt = datetime.fromisoformat(rec.timestamp)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_str = rec.timestamp
            self._set_cell(row, 0, date_str, rec.repair_type)

            # Type
            display_type = REPAIR_DISPLAY_NAMES.get(rec.repair_type, rec.repair_type.replace('_', ' ').title() if rec.repair_type else '-')
            self._set_cell(row, 1, display_type, rec.repair_type)

            # Repair #
            repair_str = str(rec.repair_number) if rec.repair_number is not None else '-'
            self._set_cell(row, 2, repair_str, rec.repair_type)

            # Duration
            mins = rec.duration / 60
            duration_str = f"{mins:.1f} min"
            self._set_cell(row, 3, duration_str, rec.repair_type, sort_value=rec.duration)

            # Frames
            self._set_cell(row, 4, str(rec.frame_count), rec.repair_type, sort_value=rec.frame_count)

            # Temperatures
            self._set_cell(row, 5, f"{rec.temp_min:.1f}", rec.repair_type, sort_value=rec.temp_min)
            self._set_cell(row, 6, f"{rec.temp_max:.1f}", rec.repair_type, sort_value=rec.temp_max)
            self._set_cell(row, 7, f"{rec.temp_avg:.1f}", rec.repair_type, sort_value=rec.temp_avg)

            # Notes (truncated)
            notes_short = rec.notes.replace('\n', ' ')[:80] if rec.notes else '-'
            item = self._set_cell(row, 8, notes_short, rec.repair_type)
            if rec.notes:
                item.setToolTip(rec.notes)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

        # Give Notes column more space
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

    def _set_cell(self, row: int, col: int, text: str, repair_type: str,
                  sort_value=None) -> QTableWidgetItem:
        """Create a table cell with optional sort value and repair type coloring."""
        item = QTableWidgetItem()
        item.setText(text)
        if sort_value is not None:
            item.setData(Qt.ItemDataRole.UserRole, sort_value)

        # Color based on repair type
        from ..theme import ThemeManager
        is_dark = ThemeManager.instance().is_dark
        colors = REPAIR_COLORS if is_dark else REPAIR_COLORS_LIGHT
        bg_hex = colors.get(repair_type)
        if bg_hex:
            item.setBackground(QColor(bg_hex))

        self.table.setItem(row, col, item)
        return item

    def apply_theme(self):
        t = current_theme()
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
