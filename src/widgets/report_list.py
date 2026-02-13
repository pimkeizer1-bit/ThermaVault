"""Reports tab: list of PDF and JSON report files with open actions."""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QTextEdit, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from ..models import ReportFile
from ..theme import current_theme


class ReportCard(QFrame):
    """A single report entry with action buttons."""

    def __init__(self, report: ReportFile, companion: ReportFile = None, parent=None):
        super().__init__(parent)
        self.report = report
        self.companion = companion
        self._init_ui()

    def _init_ui(self):
        t = current_theme()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            ReportCard {{
                background: {t.surface_bg};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Info section
        info_layout = QVBoxLayout()

        # Repair type + date
        repair_display = self.report.repair_type.replace('_', ' ').title()
        title = QLabel(f"<b>{repair_display}</b>")
        title.setStyleSheet(f"color: {t.text_primary};")
        info_layout.addWidget(title)

        # Timestamp
        ts = self.report.timestamp_str
        if len(ts) >= 15:  # YYYYMMDD_HHMMSS
            date_str = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}  {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
        else:
            date_str = ts
        date_label = QLabel(date_str)
        date_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        info_layout.addWidget(date_label)

        layout.addLayout(info_layout, 1)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)

        if self.report.is_pdf:
            open_btn = QPushButton("Open PDF")
            open_btn.setFixedWidth(100)
            open_btn.clicked.connect(self._open_pdf)
            btn_layout.addWidget(open_btn)

            if self.report.companion_path:
                data_btn = QPushButton("View Data")
                data_btn.setFixedWidth(100)
                data_btn.clicked.connect(lambda: self._view_json(self.report.companion_path))
                btn_layout.addWidget(data_btn)
        else:
            data_btn = QPushButton("View Data")
            data_btn.setFixedWidth(100)
            data_btn.clicked.connect(lambda: self._view_json(self.report.file_path))
            btn_layout.addWidget(data_btn)

            if self.report.companion_path:
                open_btn = QPushButton("Open PDF")
                open_btn.setFixedWidth(100)
                open_btn.clicked.connect(lambda: self._open_file(self.report.companion_path))
                btn_layout.addWidget(open_btn)

        layout.addLayout(btn_layout)

    def _open_pdf(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.report.file_path))

    def _open_file(self, path: str):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _view_json(self, path: str):
        """Open a dialog showing formatted JSON data."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            data = {"error": str(e)}

        dialog = JsonViewerDialog(data, Path(path).name, self)
        dialog.exec()


class JsonViewerDialog(QDialog):
    """Dialog showing formatted JSON report data."""

    def __init__(self, data: dict, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Report Data - {title}")
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        # Build readable summary
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        summary_parts = []

        # Panel info
        if 'panel' in data:
            p = data['panel']
            summary_parts.append("=== Panel ===")
            summary_parts.append(f"  Name: {p.get('name', '-')}")
            summary_parts.append(f"  ID: {p.get('panel_id', '-')}")
            if p.get('location'):
                summary_parts.append(f"  Location: {p['location']}")
            summary_parts.append("")

        # Recording summary
        if 'recording' in data:
            r = data['recording']
            summary_parts.append("=== Recording ===")
            summary_parts.append(f"  Type: {r.get('repair_type', '-')}")
            if r.get('repair_number') is not None:
                summary_parts.append(f"  Repair #: {r['repair_number']}")
            mins = r.get('duration', 0) / 60
            summary_parts.append(f"  Duration: {mins:.1f} min")
            summary_parts.append(f"  Frames: {r.get('frame_count', '-')}")
            summary_parts.append(f"  Temp Range: {r.get('temp_min', 0):.1f} - {r.get('temp_max', 0):.1f} °C")
            summary_parts.append(f"  Avg Temp: {r.get('temp_avg', 0):.1f} °C")
            summary_parts.append("")

        # Overall summary
        if 'summary' in data:
            s = data['summary']
            summary_parts.append("=== Summary ===")
            summary_parts.append(f"  Total Frames: {s.get('total_frames', '-')}")
            mins = s.get('duration', 0) / 60
            summary_parts.append(f"  Duration: {mins:.1f} min")
            summary_parts.append(f"  Temp Min: {s.get('overall_temp_min', 0):.1f} °C")
            summary_parts.append(f"  Temp Max: {s.get('overall_temp_max', 0):.1f} °C")
            summary_parts.append(f"  Temp Avg: {s.get('overall_temp_avg', 0):.1f} °C")
            summary_parts.append(f"  Temp Change: {s.get('temp_change', 0):.1f} °C")
            summary_parts.append("")

        # Zone statistics
        if 'zone_statistics' in data:
            summary_parts.append("=== Zone Statistics ===")
            for zone_name, zone_data in data['zone_statistics'].items():
                if isinstance(zone_data, dict):
                    start = zone_data.get('start_temp', zone_data.get('avg_temp', '-'))
                    end = zone_data.get('end_temp', '-')
                    change = zone_data.get('change', '-')
                    if isinstance(start, (int, float)):
                        summary_parts.append(f"  {zone_name}: {start:.1f} -> {end:.1f} °C  (change: {change:+.1f} °C)" if isinstance(change, (int, float)) else f"  {zone_name}: {start:.1f} °C")
                    else:
                        summary_parts.append(f"  {zone_name}: {start}")
            summary_parts.append("")

        # Raw JSON fallback
        summary_parts.append("=== Raw JSON ===")
        summary_parts.append(json.dumps(data, indent=2, ensure_ascii=False)[:5000])

        text_edit.setPlainText('\n'.join(summary_parts))
        layout.addWidget(text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)


class ReportListWidget(QWidget):
    """List of report files with open/view actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("No reports for this panel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {current_theme().text_muted}; padding: 40px;")
        layout.addWidget(self.empty_label)

        # Scrollable area for report cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

    def set_reports(self, reports: list[ReportFile]):
        """Populate with report files, grouping PDF + JSON companions."""
        # Clear existing cards
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not reports:
            self.empty_label.show()
            self.scroll_area.hide()
            return

        self.empty_label.hide()
        self.scroll_area.show()

        # Group by base (PDF + companion JSON shown as one card)
        seen_bases = set()
        for report in reports:
            # Create a base key to avoid duplicates
            base = f"{report.panel_id}_{report.repair_type}_{report.timestamp_str}"
            if base in seen_bases:
                continue
            seen_bases.add(base)

            # Prefer showing PDF as primary
            if report.is_pdf:
                card = ReportCard(report)
            elif report.companion_path:
                # JSON with a PDF companion - skip, the PDF entry will show both buttons
                continue
            else:
                # JSON only, no PDF
                card = ReportCard(report)

            self.scroll_layout.addWidget(card)

    def apply_theme(self):
        t = current_theme()
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
