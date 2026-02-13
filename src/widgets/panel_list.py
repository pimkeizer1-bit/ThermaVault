"""Left sidebar: searchable panel list."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

from ..models import PanelData
from ..theme import current_theme


class PanelListWidget(QWidget):
    """Searchable panel list sidebar."""

    panel_selected = pyqtSignal(str)  # Emits panel_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels: list[PanelData] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Open folder button
        self.open_btn = QPushButton("Open Folder...")
        self.open_btn.setMinimumHeight(32)
        layout.addWidget(self.open_btn)

        # Current path label
        self.path_label = QLabel("No folder selected")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet(f"color: {current_theme().text_muted}; font-size: 11px;")
        layout.addWidget(self.path_label)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search panels...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_panels)
        layout.addWidget(self.search_input)

        # Panel list
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget, 1)

        # Summary label
        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setStyleSheet(f"color: {current_theme().text_secondary}; font-size: 11px;")
        layout.addWidget(self.summary_label)

    def set_panels(self, panels: list[PanelData]):
        """Populate the list with panels."""
        self._panels = sorted(panels, key=lambda p: p.name)
        self._populate_list(self._panels)
        self._update_summary()

    def set_path(self, path: str):
        """Update the displayed path."""
        # Show abbreviated path
        if len(path) > 50:
            display = "..." + path[-47:]
        else:
            display = path
        self.path_label.setText(display)
        self.path_label.setToolTip(path)

    def _populate_list(self, panels: list[PanelData]):
        """Fill the list widget with panel items."""
        self.list_widget.clear()
        for panel in panels:
            rec_count = len(panel.recordings)
            subtitle = f"{rec_count} recording{'s' if rec_count != 1 else ''}"

            # Show repair status
            has_pre_repair = any(r.repair_type == "pre_repair" for r in panel.recordings)
            has_baseline = any(r.repair_type == "baseline" for r in panel.recordings)
            if has_pre_repair:
                subtitle += "  |  needs repair"
            elif has_baseline:
                subtitle += "  |  OK"

            item = QListWidgetItem()
            item.setText(panel.name)
            item.setToolTip(f"{panel.panel_id}\n{subtitle}\n{panel.notes}" if panel.notes else f"{panel.panel_id}\n{subtitle}")
            item.setData(Qt.ItemDataRole.UserRole, panel.panel_id)
            self.list_widget.addItem(item)

    def _filter_panels(self, text: str):
        """Filter the panel list based on search text."""
        if not text:
            self._populate_list(self._panels)
            return
        query = text.lower()
        filtered = [
            p for p in self._panels
            if (query in p.name.lower() or
                query in p.panel_id.lower() or
                query in p.location.lower() or
                any(query in tag.lower() for tag in p.tags))
        ]
        self._populate_list(filtered)

    def _on_item_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current:
            panel_id = current.data(Qt.ItemDataRole.UserRole)
            self.panel_selected.emit(panel_id)

    def _update_summary(self):
        total = len(self._panels)
        with_recordings = sum(1 for p in self._panels if p.recordings)
        self.summary_label.setText(f"{total} panels  |  {with_recordings} with recordings")

    def apply_theme(self):
        """Re-apply theme colors."""
        t = current_theme()
        self.path_label.setStyleSheet(f"color: {t.text_muted}; font-size: 11px;")
        self.summary_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
