"""Repair History tab: visual timeline of recordings."""

from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush

from ..models import RecordingData, RepairEvent
from ..theme import current_theme


# Colors for recording types
TYPE_COLORS = {
    'baseline': '#47d4a0',
    'pre_repair': '#ff6b4a',
    'post_repair': '#4e8fff',
    'followup': '#888888',
}


class TimelineCanvas(QWidget):
    """Custom-painted timeline widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recordings: list[RecordingData] = []
        self._repair_events: list[RepairEvent] = []
        self.setMinimumHeight(100)

    def set_data(self, recordings: list[RecordingData], repair_events: list[RepairEvent]):
        self._recordings = sorted(recordings, key=lambda r: r.timestamp)
        self._repair_events = repair_events
        # Set height based on content
        height = max(200, len(self._recordings) * 80 + 60)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.update()

    def paintEvent(self, event):
        if not self._recordings:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = current_theme()

        w = self.width()
        margin_left = 160
        margin_right = 40
        node_x = margin_left
        node_radius = 10
        line_x = node_x
        y_start = 30
        y_step = 80

        # Draw vertical timeline line
        pen = QPen(QColor(t.border_hover))
        pen.setWidth(2)
        painter.setPen(pen)
        y_end = y_start + (len(self._recordings) - 1) * y_step
        painter.drawLine(line_x, y_start, line_x, y_end)

        # Build repair event lookup for improvement arrows
        repair_lookup = {}
        for evt in self._repair_events:
            if evt.pre_repair:
                repair_lookup[evt.pre_repair.timestamp] = evt
            if evt.post_repair:
                repair_lookup[evt.post_repair.timestamp] = evt

        for i, rec in enumerate(self._recordings):
            y = y_start + i * y_step

            # Node circle
            color_hex = TYPE_COLORS.get(rec.repair_type, '#888888')
            node_color = QColor(color_hex)
            painter.setBrush(QBrush(node_color))
            painter.setPen(QPen(node_color.darker(120), 2))
            painter.drawEllipse(int(line_x - node_radius), int(y - node_radius),
                                node_radius * 2, node_radius * 2)

            # Date label (left of node)
            painter.setPen(QColor(t.text_secondary))
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            try:
                dt = datetime.fromisoformat(rec.timestamp)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_str = rec.timestamp[:16]
            painter.drawText(5, y + 4, date_str)

            # Type + info (right of node)
            info_x = line_x + node_radius + 15
            painter.setPen(QColor(t.text_primary))
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)

            type_display = rec.repair_type.replace('_', ' ').title() if rec.repair_type else 'Unknown'
            if rec.repair_number is not None:
                type_display += f"  #{rec.repair_number}"
            painter.drawText(info_x, y + 4, type_display)

            # Temperature info
            font.setBold(False)
            font.setPointSize(9)
            painter.setFont(font)
            painter.setPen(QColor(t.text_secondary))
            temp_str = f"Avg: {rec.temp_avg:.1f}°C  |  Range: {rec.temp_min:.1f} - {rec.temp_max:.1f}°C  |  {rec.frame_count} frames"
            painter.drawText(info_x, y + 22, temp_str)

            # Notes (if any)
            if rec.notes:
                painter.setPen(QColor(t.text_muted))
                font.setItalic(True)
                painter.setFont(font)
                notes_short = rec.notes.replace('\n', ' ')[:60]
                if len(rec.notes) > 60:
                    notes_short += "..."
                painter.drawText(info_x, y + 38, notes_short)
                font.setItalic(False)

            # Temperature improvement arrow between pre and post repair
            if rec.timestamp in repair_lookup:
                evt = repair_lookup[rec.timestamp]
                if (evt.post_repair and rec == evt.pre_repair and
                        evt.temp_improvement is not None):
                    # Draw improvement indicator
                    arrow_x = w - margin_right - 80
                    improvement = evt.temp_improvement
                    color = QColor('#47d4a0') if improvement > 0 else QColor('#ff3366')
                    painter.setPen(color)
                    font.setBold(True)
                    font.setItalic(False)
                    font.setPointSize(9)
                    painter.setFont(font)
                    sign = "+" if improvement > 0 else ""
                    painter.drawText(arrow_x, y + 4, f"{sign}{improvement:.1f}°C improvement")

        painter.end()


class RepairTimelineWidget(QWidget):
    """Scrollable repair history timeline."""

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

        # Legend
        self.legend = QLabel(
            '<span style="color: #47d4a0;">● Baseline</span>'
            '&nbsp;&nbsp;&nbsp;'
            '<span style="color: #ff6b4a;">● Pre-Repair</span>'
            '&nbsp;&nbsp;&nbsp;'
            '<span style="color: #4e8fff;">● Post-Repair</span>'
            '&nbsp;&nbsp;&nbsp;'
            '<span style="color: #888888;">● Follow-up</span>'
        )
        self.legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legend.setStyleSheet("padding: 8px;")
        layout.addWidget(self.legend)

        # Scrollable canvas
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.canvas = TimelineCanvas()
        self.scroll_area.setWidget(self.canvas)
        layout.addWidget(self.scroll_area, 1)

    def set_data(self, recordings: list[RecordingData], repair_events: list[RepairEvent]):
        if not recordings:
            self.empty_label.show()
            self.legend.hide()
            self.scroll_area.hide()
            return

        self.empty_label.hide()
        self.legend.show()
        self.scroll_area.show()
        self.canvas.set_data(recordings, repair_events)

    def apply_theme(self):
        t = current_theme()
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
