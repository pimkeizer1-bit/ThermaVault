"""Right side: tabbed panel detail view."""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTabWidget, QFormLayout, QFrame,
    QHBoxLayout
)
from PyQt6.QtCore import Qt

from ..models import PanelData, ReportFile, RecordingData
from ..theme import current_theme
from .recording_table import RecordingTableWidget
from .recording_viewer import RecordingViewerWidget
from .report_list import ReportListWidget
from .repair_timeline import RepairTimelineWidget
from .qr_display import QRDisplayWidget


class PanelDetailWidget(QWidget):
    """Tabbed detail view for a selected panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qr_dir: str | None = None
        self._init_ui()

    def set_qr_dir(self, qr_dir: str):
        """Set the QR codes directory path (for saving generated QR codes)."""
        self._qr_dir = qr_dir

    def set_settings(self, settings):
        """Pass settings reference to child widgets that need it."""
        self.playback_tab.set_settings(settings)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        self.header_frame = QFrame()
        header_layout = QVBoxLayout(self.header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)

        self.name_label = QLabel("Select a panel")
        self.name_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {current_theme().text_primary};")
        header_layout.addWidget(self.name_label)

        self.id_label = QLabel("")
        self.id_label.setStyleSheet(f"font-size: 12px; color: {current_theme().text_secondary};")
        header_layout.addWidget(self.id_label)

        layout.addWidget(self.header_frame)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Details tab
        self.details_tab = self._create_details_tab()
        self.tabs.addTab(self.details_tab, "Details")

        # Recordings tab (table)
        self.recordings_tab = RecordingTableWidget()
        self.tabs.addTab(self.recordings_tab, "Recordings")

        # Playback tab (thermal viewer)
        self.playback_tab = RecordingViewerWidget()
        self.tabs.addTab(self.playback_tab, "Playback")

        # Reports tab
        self.reports_tab = ReportListWidget()
        self.tabs.addTab(self.reports_tab, "Reports")

        # Repair History tab
        self.repair_tab = RepairTimelineWidget()
        self.tabs.addTab(self.repair_tab, "Repair History")

        # QR Code tab
        self.qr_tab = QRDisplayWidget()
        self.tabs.addTab(self.qr_tab, "QR Code")

        # Initially hide tabs
        self.tabs.hide()

    def _create_details_tab(self) -> QWidget:
        """Create the Details tab with panel metadata."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        t = current_theme()
        label_style = f"color: {t.text_secondary}; font-weight: bold;"
        value_style = f"color: {t.text_primary};"

        self._detail_fields = {}
        fields = [
            ('name', 'Name'),
            ('panel_id', 'Panel ID'),
            ('location', 'Location'),
            ('manufacturer', 'Manufacturer'),
            ('model', 'Model'),
            ('serial_number', 'Serial Number'),
            ('rated_power', 'Rated Power'),
            ('installation_date', 'Installation Date'),
            ('created_date', 'Created'),
            ('notes', 'Notes'),
            ('tags', 'Tags'),
            ('recording_count', 'Recordings'),
        ]

        for key, label_text in fields:
            label = QLabel(f"{label_text}:")
            label.setStyleSheet(label_style)
            value = QLabel("-")
            value.setStyleSheet(value_style)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, value)
            self._detail_fields[key] = value

        layout.addLayout(form)
        layout.addStretch()
        return widget

    def set_panel(self, panel: PanelData, reports: list[ReportFile],
                  repair_events: list, qr_path: str | None):
        """Populate all tabs with panel data."""
        t = current_theme()

        # Header
        self.name_label.setText(panel.name)
        self.name_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {t.text_primary};")
        self.id_label.setText(panel.panel_id)
        self.id_label.setStyleSheet(f"font-size: 12px; color: {t.text_secondary};")

        # Show tabs
        self.tabs.show()

        # Details tab
        self._detail_fields['name'].setText(panel.name)
        self._detail_fields['panel_id'].setText(panel.panel_id)
        self._detail_fields['location'].setText(panel.location or '-')
        self._detail_fields['manufacturer'].setText(panel.manufacturer or '-')
        self._detail_fields['model'].setText(panel.model or '-')
        self._detail_fields['serial_number'].setText(panel.serial_number or '-')
        self._detail_fields['rated_power'].setText(f"{panel.rated_power} W" if panel.rated_power else '-')
        self._detail_fields['installation_date'].setText(panel.installation_date or '-')

        # Format created date
        if panel.created_date:
            try:
                dt = datetime.fromisoformat(panel.created_date)
                self._detail_fields['created_date'].setText(dt.strftime("%Y-%m-%d %H:%M"))
            except (ValueError, TypeError):
                self._detail_fields['created_date'].setText(panel.created_date)
        else:
            self._detail_fields['created_date'].setText('-')

        self._detail_fields['notes'].setText(panel.notes or '-')
        self._detail_fields['tags'].setText(', '.join(panel.tags) if panel.tags else '-')
        self._detail_fields['recording_count'].setText(str(len(panel.recordings)))

        # Recordings tab (table)
        self.recordings_tab.set_recordings(panel.recordings)

        # Playback tab (thermal viewer)
        self.playback_tab.set_panel_recordings(panel.panel_id, panel.recordings)

        # Reports tab
        self.reports_tab.set_reports(reports)

        # Repair History tab
        self.repair_tab.set_data(panel.recordings, repair_events)

        # QR Code tab - pass panel data for auto-generation
        self.qr_tab.set_qr_data(panel, qr_path, self._qr_dir)

        # Update tab labels with counts
        self.tabs.setTabText(1, f"Recordings ({len(panel.recordings)})")
        pdf_count = len([r for r in reports if r.is_pdf])
        self.tabs.setTabText(3, f"Reports ({pdf_count})")

    def set_temp_range(self, temp_min: float, temp_max: float):
        """Forward the global temperature range to the playback tab."""
        self.playback_tab.set_temp_range(temp_min, temp_max)

    def clear(self):
        """Reset to empty state."""
        self.name_label.setText("Select a panel")
        self.id_label.setText("")
        self.tabs.hide()
        self.playback_tab.clear()

    def apply_theme(self):
        t = current_theme()
        self.name_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {t.text_primary};")
        self.id_label.setStyleSheet(f"font-size: 12px; color: {t.text_secondary};")
        self.recordings_tab.apply_theme()
        self.playback_tab.apply_theme()
        self.reports_tab.apply_theme()
        self.repair_tab.apply_theme()
        self.qr_tab.apply_theme()
