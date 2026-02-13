"""Recording viewer tab: load and play back thermal recordings for a specific panel."""

from pathlib import Path
from datetime import datetime, date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QComboBox, QCheckBox, QSizePolicy, QFrame, QDialog, QSpinBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QPainterPath

import numpy as np
import cv2

from ..recording_loader import RecordingLoader
from ..theme import current_theme


def _recording_label(rec) -> str:
    """Build a human-readable label for a recording."""
    try:
        dt = datetime.fromisoformat(rec.timestamp)
        return f"{dt.strftime('%Y-%m-%d %H:%M')} - {rec.repair_type.replace('_', ' ').title()}"
    except (ValueError, TypeError):
        return rec.recording_id


class ThermalFrameDisplay(QLabel):
    """Widget that displays a thermal RGB frame scaled to fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(100, 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pixmap = None

    def set_frame(self, rgb: np.ndarray):
        """Display an RGB numpy array (H, W, 3) uint8."""
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self._update_display()

    def _update_display(self):
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            super().setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def clear_frame(self):
        self._pixmap = None
        super().clear()


class TemperatureGraphWidget(QWidget):
    """Shows temperature min/max/avg over time for a recording."""

    frame_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setMaximumHeight(160)
        self._mins = []
        self._maxs = []
        self._avgs = []
        self._timestamps = []
        self._current_frame = 0
        self._frame_count = 0

    def set_data(self, mins, maxs, avgs, timestamps):
        self._mins = mins
        self._maxs = maxs
        self._avgs = avgs
        self._timestamps = timestamps
        self._frame_count = len(mins)
        self.update()

    def set_current_frame(self, index):
        self._current_frame = index
        self.update()

    def clear_data(self):
        self._mins = []
        self._maxs = []
        self._avgs = []
        self._timestamps = []
        self._frame_count = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        t = current_theme()
        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(self.rect(), QColor(t.surface_bg))

        if not self._mins:
            painter.setPen(QColor(t.text_muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Temperature graph will appear when a recording is loaded")
            painter.end()
            return

        # Margins
        left_margin = 50
        right_margin = 60
        top_margin = 10
        bottom_margin = 20

        plot_w = w - left_margin - right_margin
        plot_h = h - top_margin - bottom_margin

        if plot_w <= 0 or plot_h <= 0:
            painter.end()
            return

        # Data range with padding
        data_min = min(self._mins)
        data_max = max(self._maxs)
        temp_range = data_max - data_min
        if temp_range < 1:
            temp_range = 1
        data_min -= temp_range * 0.05
        data_max += temp_range * 0.05
        temp_range = data_max - data_min

        n = self._frame_count

        def x_pos(i):
            return left_margin + (i / max(1, n - 1)) * plot_w

        def y_pos(temp):
            return top_margin + plot_h - ((temp - data_min) / temp_range) * plot_h

        # Grid lines (horizontal)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        for i in range(5):
            temp = data_min + (i / 4.0) * temp_range
            y = y_pos(temp)
            painter.setPen(QPen(QColor(t.border), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(left_margin, y), QPointF(left_margin + plot_w, y))
            painter.setPen(QColor(t.text_secondary))
            painter.drawText(2, int(y + 4), f"{temp:.1f}")

        # Filled area between min and max
        if n > 1:
            path = QPainterPath()
            path.moveTo(QPointF(x_pos(0), y_pos(self._maxs[0])))
            for i in range(1, n):
                path.lineTo(QPointF(x_pos(i), y_pos(self._maxs[i])))
            for i in range(n - 1, -1, -1):
                path.lineTo(QPointF(x_pos(i), y_pos(self._mins[i])))
            path.closeSubpath()

            painter.setBrush(QColor(70, 130, 180, 50))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)

        # Max line (red)
        pen = QPen(QColor(255, 100, 100), 1)
        painter.setPen(pen)
        for i in range(1, n):
            painter.drawLine(QPointF(x_pos(i-1), y_pos(self._maxs[i-1])),
                           QPointF(x_pos(i), y_pos(self._maxs[i])))

        # Min line (blue)
        pen = QPen(QColor(100, 130, 255), 1)
        painter.setPen(pen)
        for i in range(1, n):
            painter.drawLine(QPointF(x_pos(i-1), y_pos(self._mins[i-1])),
                           QPointF(x_pos(i), y_pos(self._mins[i])))

        # Avg line (yellow)
        pen = QPen(QColor(255, 220, 100), 2)
        painter.setPen(pen)
        for i in range(1, n):
            painter.drawLine(QPointF(x_pos(i-1), y_pos(self._avgs[i-1])),
                           QPointF(x_pos(i), y_pos(self._avgs[i])))

        # Current frame marker (white vertical line)
        if 0 <= self._current_frame < n:
            pen = QPen(QColor(255, 255, 255, 200), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            cx = x_pos(self._current_frame)
            painter.drawLine(QPointF(cx, top_margin), QPointF(cx, top_margin + plot_h))

        # X-axis: frame numbers
        painter.setPen(QColor(t.text_secondary))
        step = max(1, n // 6)
        for i in range(0, n, step):
            x = x_pos(i)
            painter.drawText(int(x - 10), h - 2, f"{i}")

        # Legend (right side)
        legend_x = left_margin + plot_w + 8
        legend_y = top_margin + 14

        painter.setPen(QColor(255, 100, 100))
        painter.drawText(legend_x, legend_y, "Max")
        painter.setPen(QColor(255, 220, 100))
        painter.drawText(legend_x, legend_y + 14, "Avg")
        painter.setPen(QColor(100, 130, 255))
        painter.drawText(legend_x, legend_y + 28, "Min")

        # Border around plot area
        pen = QPen(QColor(t.border), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(left_margin, top_margin, plot_w, plot_h)

        painter.end()

    def mousePressEvent(self, event):
        if not self._mins or event.button() != Qt.MouseButton.LeftButton:
            return

        left_margin = 50
        right_margin = 60
        plot_w = self.width() - left_margin - right_margin

        if plot_w <= 0:
            return

        x = event.pos().x() - left_margin
        frame = int(x / plot_w * self._frame_count)
        frame = max(0, min(frame, self._frame_count - 1))
        self.frame_clicked.emit(frame)


class CompareSelectDialog(QDialog):
    """Dialog to select which recordings to compare."""

    def __init__(self, recordings: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Recordings to Compare")
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select which recordings to show side by side:"))

        self._checkboxes: list[QCheckBox] = []
        for rec in recordings:
            cb = QCheckBox(_recording_label(rec))
            cb.setChecked(True)
            self._checkboxes.append(cb)
            layout.addWidget(cb)

        # Select all / none
        btn_row = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all(True))
        btn_row.addWidget(select_all)

        select_none = QPushButton("Select None")
        select_none.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(select_none)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # OK / Cancel
        action_row = QHBoxLayout()
        action_row.addStretch()

        ok_btn = QPushButton("Compare")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        action_row.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        action_row.addWidget(cancel_btn)

        layout.addLayout(action_row)

    def _set_all(self, checked: bool):
        for cb in self._checkboxes:
            cb.setChecked(checked)

    def selected_indices(self) -> list[int]:
        return [i for i, cb in enumerate(self._checkboxes) if cb.isChecked()]


class ComparisonPanel(QFrame):
    """One panel in the comparison view with its own loader and controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: RecordingLoader | None = None
        self._panel_id: str = ""
        self._current_frame: int = 0
        self._frame_count: int = 0

        t = current_theme()
        self.setStyleSheet(
            f"ComparisonPanel {{ border: 1px solid {t.border}; border-radius: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Title label
        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            f"font-weight: bold; font-size: 11px; color: {t.text_primary};"
        )
        layout.addWidget(self.title_label)

        # Frame display
        self.display = ThermalFrameDisplay()
        layout.addWidget(self.display, 1)

        # Stats
        self.stats_label = QLabel("")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 10px;")
        layout.addWidget(self.stats_label)

        # Frame counter
        self.frame_label = QLabel("0 / 0")
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_label.setStyleSheet(f"font-size: 10px; color: {t.text_secondary};")
        layout.addWidget(self.frame_label)

        # Status label (shown when recording not available)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

    def load_recording(self, recording_path: str, panel_id: str,
                       title: str, temp_min: float, temp_max: float,
                       colormap_scheme: str) -> bool:
        """Load a recording for this comparison panel."""
        self._panel_id = panel_id
        self.title_label.setText(title)

        if self._loader:
            self._loader.close()

        recording_path = recording_path.replace('/', '\\')
        self._loader = RecordingLoader(recording_path)

        if not self._loader.load():
            self._show_status("Recording files not found")
            return False

        if not self._loader.find_panel_in_recording(panel_id):
            self._show_status("Panel not in this recording")
            self._loader.close()
            self._loader = None
            return False

        self._loader.set_colormap(temp_min, temp_max, colormap_scheme)

        self._frame_count = self._loader.get_frame_count()
        self._current_frame = 0

        self.status_label.hide()
        self.display.show()
        self.frame_label.show()
        self.stats_label.show()

        self._show_frame(0)
        return True

    def _show_status(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.show()
        self.display.clear_frame()
        self.stats_label.setText("")
        self.frame_label.setText("")

    def _show_frame(self, index: int):
        if self._loader is None:
            return
        rgb = self._loader.get_panel_frame(index, self._panel_id)
        if rgb is None:
            return
        rgb = np.ascontiguousarray(rgb)
        self.display.set_frame(rgb)

        stats = self._loader.get_frame_stats(index, self._panel_id)
        if stats:
            self.stats_label.setText(
                f"Min: {stats['min']:.1f}  |  Max: {stats['max']:.1f}  |  "
                f"Avg: {stats['avg']:.1f} \u00b0C"
            )

        self.frame_label.setText(f"{index + 1} / {self._frame_count}")

    def get_frame_count(self) -> int:
        return self._frame_count

    def set_frame(self, index: int):
        """Set frame from external control (synchronized playback)."""
        if self._loader is None or self._frame_count == 0:
            return
        clamped = min(index, self._frame_count - 1)
        self._current_frame = clamped
        self._show_frame(clamped)

    def close_loader(self):
        if self._loader:
            self._loader.close()
            self._loader = None

    def apply_theme(self):
        t = current_theme()
        self.setStyleSheet(
            f"ComparisonPanel {{ border: 1px solid {t.border}; border-radius: 4px; }}"
        )
        self.title_label.setStyleSheet(
            f"font-weight: bold; font-size: 11px; color: {t.text_primary};"
        )
        self.stats_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 10px;")
        self.frame_label.setStyleSheet(f"font-size: 10px; color: {t.text_secondary};")
        self.status_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")


class RecordingViewerWidget(QWidget):
    """Full recording viewer with playback controls, side-by-side original view,
    and multi-recording comparison."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: RecordingLoader | None = None
        self._panel_id: str = ""
        self._current_frame: int = 0
        self._playing: bool = False
        self._playback_speed: float = 1.0
        self._recordings: list = []
        self._comparison_panels: list[ComparisonPanel] = []
        self._compare_playing: bool = False
        self._compare_frame: int = 0
        self._settings = None
        self._current_recording_id: str = ""

        # Global temperature range (set by main window)
        self._temp_min: float = 10.0
        self._temp_max: float = 130.0
        self._colormap_scheme: str = "ironbow"

        # Swap dimensions state
        self._swap_dimensions: bool = False

        # Grid state
        self._show_grid: bool = False
        self._grid_rows: int = 3
        self._grid_cols: int = 6

        self._play_timer = QTimer()
        self._play_timer.timeout.connect(self._advance_frame)

        self._compare_timer = QTimer()
        self._compare_timer.timeout.connect(self._advance_compare_frame)

        self._init_ui()

    def set_settings(self, settings):
        """Set the settings reference for verified recordings."""
        self._settings = settings

    def set_temp_range(self, temp_min: float, temp_max: float):
        """Set the global temperature range for colormapping."""
        self._temp_min = temp_min
        self._temp_max = temp_max
        if self._loader:
            self._loader.set_colormap(temp_min, temp_max, self._colormap_scheme)
            self._show_frame(self._current_frame)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        t = current_theme()

        # Recording selector (always at top, outside viewer_container)
        selector_bar = QHBoxLayout()
        self.recording_selector_label = QLabel("Recording:")
        self.recording_combo = QComboBox()
        self.recording_combo.currentIndexChanged.connect(self._on_recording_selected)
        selector_bar.addWidget(self.recording_selector_label)
        selector_bar.addWidget(self.recording_combo, 1)

        self.compare_btn = QPushButton("Compare...")
        self.compare_btn.setToolTip("Select recordings to compare side by side")
        self.compare_btn.setFixedWidth(100)
        self.compare_btn.clicked.connect(self._open_compare_dialog)
        selector_bar.addWidget(self.compare_btn)

        self.recording_selector_label.hide()
        self.recording_combo.hide()
        self.compare_btn.hide()
        layout.addLayout(selector_bar)

        # Empty state
        self.empty_label = QLabel("Select a recording to view the thermal playback")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
        layout.addWidget(self.empty_label)

        # === Single recording viewer ===
        self.viewer_container = QWidget()
        viewer_layout = QVBoxLayout(self.viewer_container)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(6)

        # Warning banner for old recordings
        self.warning_banner = QFrame()
        self.warning_banner.setStyleSheet(
            "QFrame { background-color: #7a6520; border: 1px solid #b8981f; "
            "border-radius: 4px; padding: 6px; }"
        )
        warning_layout = QHBoxLayout(self.warning_banner)
        warning_layout.setContentsMargins(10, 6, 10, 6)

        self.warning_text = QLabel(
            "[Warning] This recording was made during testing (before 2026-02-13). "
            "Data may contain errors or inconsistencies."
        )
        self.warning_text.setWordWrap(True)
        self.warning_text.setStyleSheet("color: #ffd54f; font-size: 11px; background: transparent;")
        warning_layout.addWidget(self.warning_text, 1)

        self.verify_btn = QPushButton("Mark as Verified")
        self.verify_btn.setFixedWidth(130)
        self.verify_btn.setToolTip("Dismiss this warning for this recording")
        self.verify_btn.clicked.connect(self._mark_verified)
        self.verify_btn.setStyleSheet(
            "QPushButton { background-color: #5d4e11; color: #ffd54f; "
            "border: 1px solid #b8981f; }"
        )
        warning_layout.addWidget(self.verify_btn)

        self.warning_banner.hide()
        viewer_layout.addWidget(self.warning_banner)

        # Top bar: recording info + options
        info_bar = QHBoxLayout()
        self.recording_label = QLabel("")
        self.recording_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        info_bar.addWidget(self.recording_label)
        info_bar.addStretch()

        # Swap dimensions button
        self.swap_btn = QPushButton("Swap W/H")
        self.swap_btn.setToolTip("Swap width and height of the panel view")
        self.swap_btn.setFixedWidth(80)
        self.swap_btn.setCheckable(True)
        self.swap_btn.toggled.connect(self._on_swap_toggled)
        info_bar.addWidget(self.swap_btn)

        # Grid overlay controls
        self.grid_cb = QCheckBox("Grid")
        self.grid_cb.setToolTip("Show grid overlay with cell temperature stats")
        self.grid_cb.toggled.connect(self._on_grid_toggled)
        info_bar.addWidget(self.grid_cb)

        self.grid_rows_spin = QSpinBox()
        self.grid_rows_spin.setRange(1, 12)
        self.grid_rows_spin.setValue(3)
        self.grid_rows_spin.setFixedWidth(45)
        self.grid_rows_spin.setToolTip("Grid rows")
        self.grid_rows_spin.valueChanged.connect(self._on_grid_size_changed)
        info_bar.addWidget(self.grid_rows_spin)

        info_bar.addWidget(QLabel("x"))

        self.grid_cols_spin = QSpinBox()
        self.grid_cols_spin.setRange(1, 12)
        self.grid_cols_spin.setValue(6)
        self.grid_cols_spin.setFixedWidth(45)
        self.grid_cols_spin.setToolTip("Grid columns")
        self.grid_cols_spin.valueChanged.connect(self._on_grid_size_changed)
        info_bar.addWidget(self.grid_cols_spin)

        # Show original checkbox
        self.show_original_cb = QCheckBox("Show original")
        self.show_original_cb.setToolTip("Show the full recording frame alongside the corrected panel view")
        self.show_original_cb.toggled.connect(self._on_show_original_changed)
        info_bar.addWidget(self.show_original_cb)

        # Colormap selector
        info_bar.addWidget(QLabel("Colormap:"))
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItems(["ironbow", "rainbow", "hot", "cool_warm", "plasma", "grayscale"])
        self.colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
        info_bar.addWidget(self.colormap_combo)

        viewer_layout.addLayout(info_bar)

        # Frame display area
        self.display_container = QHBoxLayout()
        self.display_container.setSpacing(8)

        self.original_display = ThermalFrameDisplay()
        self.original_display.hide()
        self.display_container.addWidget(self.original_display, 1)

        self.frame_display = ThermalFrameDisplay()
        self.display_container.addWidget(self.frame_display, 1)

        viewer_layout.addLayout(self.display_container, 1)

        # Labels under each display
        self.display_labels = QHBoxLayout()
        self.display_labels.setSpacing(8)

        self.original_frame_label = QLabel("Original (with ROI)")
        self.original_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_frame_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
        self.original_frame_label.hide()
        self.display_labels.addWidget(self.original_frame_label, 1)

        self.corrected_frame_label = QLabel("Corrected panel view")
        self.corrected_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.corrected_frame_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
        self.corrected_frame_label.hide()
        self.display_labels.addWidget(self.corrected_frame_label, 1)

        viewer_layout.addLayout(self.display_labels)

        # Stats bar
        self.stats_label = QLabel("")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_label.setStyleSheet(
            f"color: {t.text_primary}; background: {t.surface_bg}; "
            f"border: 1px solid {t.border}; border-radius: 4px; padding: 6px;"
        )
        viewer_layout.addWidget(self.stats_label)

        # Temperature graph
        self.temp_graph = TemperatureGraphWidget()
        self.temp_graph.frame_clicked.connect(self._on_graph_frame_clicked)
        viewer_layout.addWidget(self.temp_graph)

        # Playback controls
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(80)
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.valueChanged.connect(self._on_slider_changed)
        controls.addWidget(self.frame_slider, 1)

        self.frame_label = QLabel("0 / 0")
        self.frame_label.setFixedWidth(80)
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls.addWidget(self.frame_label)

        self.time_label = QLabel("0:00")
        self.time_label.setFixedWidth(60)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls.addWidget(self.time_label)

        controls.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1x", "2x", "4x", "8x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        self.speed_combo.setFixedWidth(60)
        controls.addWidget(self.speed_combo)

        viewer_layout.addLayout(controls)

        layout.addWidget(self.viewer_container)
        self.viewer_container.hide()

        # === Comparison view ===
        self.comparison_wrapper = QWidget()
        comparison_wrapper_layout = QVBoxLayout(self.comparison_wrapper)
        comparison_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        comparison_wrapper_layout.setSpacing(6)

        # Panels row
        self.comparison_panels_widget = QWidget()
        self.comparison_layout = QHBoxLayout(self.comparison_panels_widget)
        self.comparison_layout.setContentsMargins(0, 0, 0, 0)
        self.comparison_layout.setSpacing(8)
        comparison_wrapper_layout.addWidget(self.comparison_panels_widget, 1)

        # Synchronized playback controls
        compare_controls = QHBoxLayout()
        compare_controls.setSpacing(8)

        self.compare_play_btn = QPushButton("Play All")
        self.compare_play_btn.setFixedWidth(80)
        self.compare_play_btn.clicked.connect(self._toggle_compare_play)
        compare_controls.addWidget(self.compare_play_btn)

        self.compare_slider = QSlider(Qt.Orientation.Horizontal)
        self.compare_slider.setMinimum(0)
        self.compare_slider.valueChanged.connect(self._on_compare_slider_changed)
        compare_controls.addWidget(self.compare_slider, 1)

        self.compare_frame_label = QLabel("0 / 0")
        self.compare_frame_label.setFixedWidth(80)
        self.compare_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        compare_controls.addWidget(self.compare_frame_label)

        compare_controls.addWidget(QLabel("Speed:"))
        self.compare_speed_combo = QComboBox()
        self.compare_speed_combo.addItems(["0.5x", "1x", "2x", "4x", "8x"])
        self.compare_speed_combo.setCurrentText("1x")
        self.compare_speed_combo.currentTextChanged.connect(self._on_compare_speed_changed)
        self.compare_speed_combo.setFixedWidth(60)
        compare_controls.addWidget(self.compare_speed_combo)

        comparison_wrapper_layout.addLayout(compare_controls)

        layout.addWidget(self.comparison_wrapper)
        self.comparison_wrapper.hide()

    # -- Panel recordings setup --

    def set_panel_recordings(self, panel_id: str, recordings: list):
        """Set up the viewer with a panel's recordings."""
        self._panel_id = panel_id
        self._recordings = recordings
        self._stop_playback()
        self._stop_compare_playback()
        self._clear_comparison()

        self.recording_combo.blockSignals(True)
        self.recording_combo.clear()

        if not recordings:
            self.empty_label.setText("No recordings for this panel")
            self.empty_label.show()
            self.viewer_container.hide()
            self.comparison_wrapper.hide()
            self.recording_selector_label.hide()
            self.recording_combo.hide()
            self.compare_btn.hide()
            return

        # Build combo and find first recording that contains this panel
        first_valid_index = -1
        for i, rec in enumerate(recordings):
            self.recording_combo.addItem(_recording_label(rec), rec.recording_path)

            if first_valid_index < 0:
                test_loader = RecordingLoader(rec.recording_path.replace('/', '\\'))
                if test_loader.load() and test_loader.find_panel_in_recording(panel_id):
                    first_valid_index = i
                test_loader.close()

        self.recording_combo.blockSignals(False)

        has_multiple = len(recordings) > 1
        self.recording_selector_label.setVisible(has_multiple)
        self.recording_combo.setVisible(has_multiple)
        self.compare_btn.setVisible(has_multiple)

        load_index = first_valid_index if first_valid_index >= 0 else 0
        self.recording_combo.blockSignals(True)
        self.recording_combo.setCurrentIndex(load_index)
        self.recording_combo.blockSignals(False)
        self._load_recording(self._recordings[load_index])

    # -- Single recording --

    def _load_recording(self, recording):
        """Load a recording. Accepts a RecordingData object."""
        self._stop_playback()
        self._stop_compare_playback()
        self._clear_comparison()

        if self._loader:
            self._loader.close()

        recording_path = recording.recording_path
        self._current_recording_id = recording.recording_id

        recording_path = recording_path.replace('/', '\\')

        self._loader = RecordingLoader(recording_path)
        if not self._loader.load():
            self.empty_label.setText(
                f"Could not load recording:\n{Path(recording_path).name}\n\n"
                "The recording files may be missing or corrupted."
            )
            self.empty_label.show()
            self.viewer_container.hide()
            return

        if not self._loader.find_panel_in_recording(self._panel_id):
            self.empty_label.setText(
                f"This panel's ROI was not found in recording:\n"
                f"{Path(recording_path).name}\n\n"
                "Try selecting a different recording from the dropdown."
            )
            self.empty_label.show()
            self.viewer_container.hide()
            return

        self._loader.set_colormap(self._temp_min, self._temp_max, self._colormap_scheme)

        frame_count = self._loader.get_frame_count()
        self.frame_slider.setMaximum(max(0, frame_count - 1))
        self.frame_slider.setValue(0)
        self._current_frame = 0

        meta = self._loader.metadata
        self.recording_label.setText(
            f"{meta.name}  |  {frame_count} frames  |  "
            f"{meta.duration_seconds / 60:.1f} min  |  "
            f"Range: {self._temp_min:.0f} - {self._temp_max:.0f} \u00b0C"
        )

        # Check if this recording needs a warning banner
        self._update_warning_banner()

        self.empty_label.hide()
        self.comparison_wrapper.hide()
        self.viewer_container.show()
        self._show_frame(0)

        # Compute temperature graph data
        self._compute_temp_graph()

    def _update_warning_banner(self):
        """Show/hide the warning banner based on recording date and verified status."""
        if self._loader is None or self._loader.metadata is None:
            self.warning_banner.hide()
            return

        # Check if recording is from before today (2026-02-13)
        try:
            rec_dt = datetime.fromisoformat(self._loader.metadata.start_time)
            is_old = rec_dt.date() < date(2026, 2, 13)
        except (ValueError, TypeError):
            is_old = True

        # Check if it's been verified
        is_verified = False
        if self._settings and self._current_recording_id:
            is_verified = self._settings.is_recording_verified(self._current_recording_id)

        self.warning_banner.setVisible(is_old and not is_verified)

    def _mark_verified(self):
        """Mark the current recording as verified, hiding the warning."""
        if self._settings and self._current_recording_id:
            self._settings.add_verified_recording(self._current_recording_id)
            self.warning_banner.hide()

    def _compute_temp_graph(self):
        """Compute temperature stats for all frames and update the graph."""
        if self._loader is None:
            self.temp_graph.clear_data()
            return

        stats = self._loader.get_all_frame_stats(self._panel_id)
        if stats:
            self.temp_graph.set_data(
                stats['mins'], stats['maxs'], stats['avgs'], stats['timestamps']
            )
        else:
            self.temp_graph.clear_data()

    def _show_frame(self, index: int):
        if self._loader is None:
            return

        # Get raw corrected temperature data
        raw_corrected = self._loader.get_panel_raw_corrected(index, self._panel_id)
        if raw_corrected is None:
            return

        # Apply swap if enabled
        if self._swap_dimensions:
            raw_corrected = cv2.rotate(raw_corrected, cv2.ROTATE_90_CLOCKWISE)

        # Apply colormap
        rgb = self._loader.colormap_apply(raw_corrected)
        if rgb is None:
            return

        # Draw grid overlay if enabled
        if self._show_grid:
            self._draw_grid_overlay(rgb, raw_corrected, self._grid_rows, self._grid_cols)

        rgb = np.ascontiguousarray(rgb)
        self.frame_display.set_frame(rgb)

        if self.show_original_cb.isChecked():
            full_rgb = self._loader.get_full_frame_rgb(index, highlight_panel_id=self._panel_id)
            if full_rgb is not None:
                full_rgb = np.ascontiguousarray(full_rgb)
                self.original_display.set_frame(full_rgb)

        # Stats from the (possibly swapped) raw data
        self.stats_label.setText(
            f"Min: {float(np.min(raw_corrected)):.1f} \u00b0C  |  "
            f"Max: {float(np.max(raw_corrected)):.1f} \u00b0C  |  "
            f"Avg: {float(np.mean(raw_corrected)):.1f} \u00b0C"
        )

        total = self._loader.get_frame_count()
        self.frame_label.setText(f"{index + 1} / {total}")

        timestamp = self._loader.get_timestamp(index)
        mins = int(timestamp // 60)
        secs = int(timestamp % 60)
        self.time_label.setText(f"{mins}:{secs:02d}")

        # Update graph marker
        self.temp_graph.set_current_frame(index)

    def _draw_grid_overlay(self, rgb: np.ndarray, raw: np.ndarray,
                           rows: int, cols: int):
        """Draw grid lines and cell temperature stats on the RGB frame."""
        h, w = rgb.shape[:2]
        line_color = (200, 200, 200)

        # Vertical lines
        for i in range(1, cols):
            x = int(i * w / cols)
            cv2.line(rgb, (x, 0), (x, h - 1), line_color, 1)

        # Horizontal lines
        for i in range(1, rows):
            y = int(i * h / rows)
            cv2.line(rgb, (0, y), (w - 1, y), line_color, 1)

        # Cell stats
        font = cv2.FONT_HERSHEY_SIMPLEX
        cell_h = h / rows
        cell_w = w / cols

        # Determine font scale based on cell size
        font_scale = min(cell_w, cell_h) / 120.0
        font_scale = max(0.25, min(font_scale, 0.5))

        for r in range(rows):
            for c in range(cols):
                y1 = int(r * h / rows)
                y2 = int((r + 1) * h / rows)
                x1 = int(c * w / cols)
                x2 = int((c + 1) * w / cols)

                cell = raw[y1:y2, x1:x2]
                if cell.size == 0:
                    continue

                cell_min = float(np.min(cell))
                cell_max = float(np.max(cell))
                cell_avg = float(np.mean(cell))

                # Zone label (A1, B2, etc.)
                zone = f"{chr(65 + r)}{c + 1}"
                cv2.putText(rgb, zone, (x1 + 2, y1 + int(12 * font_scale / 0.3)),
                            font, font_scale * 0.9, (255, 255, 255), 1)

                # Stats text
                cy = (y1 + y2) // 2
                line_h = int(14 * font_scale / 0.3)
                cv2.putText(rgb, f"H {cell_max:.1f}", (x1 + 2, cy - line_h // 2),
                            font, font_scale, (255, 100, 100), 1)
                cv2.putText(rgb, f"~ {cell_avg:.1f}", (x1 + 2, cy + line_h // 4),
                            font, font_scale, (255, 255, 255), 1)
                cv2.putText(rgb, f"L {cell_min:.1f}", (x1 + 2, cy + line_h),
                            font, font_scale, (100, 150, 255), 1)

    def _on_swap_toggled(self, checked: bool):
        self._swap_dimensions = checked
        self._show_frame(self._current_frame)

    def _on_grid_toggled(self, checked: bool):
        self._show_grid = checked
        self._show_frame(self._current_frame)

    def _on_grid_size_changed(self):
        self._grid_rows = self.grid_rows_spin.value()
        self._grid_cols = self.grid_cols_spin.value()
        if self._show_grid:
            self._show_frame(self._current_frame)

    def _on_graph_frame_clicked(self, frame_index: int):
        """Seek to a frame when the user clicks on the temperature graph."""
        self._current_frame = frame_index
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(frame_index)
        self.frame_slider.blockSignals(False)
        self._show_frame(frame_index)

    def _on_show_original_changed(self, checked: bool):
        self.original_display.setVisible(checked)
        self.original_frame_label.setVisible(checked)
        self.corrected_frame_label.setVisible(checked)
        if checked:
            self._show_frame(self._current_frame)
        else:
            self.original_display.clear_frame()

    def _on_slider_changed(self, value: int):
        self._current_frame = value
        self._show_frame(value)

    def _toggle_play(self):
        if self._playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        if self._loader is None:
            return
        self._playing = True
        self.play_btn.setText("Pause")
        interval_ms = max(30, int(500 / self._playback_speed))
        self._play_timer.start(interval_ms)

    def _stop_playback(self):
        self._playing = False
        self._play_timer.stop()
        self.play_btn.setText("Play")

    def _advance_frame(self):
        if self._loader is None:
            self._stop_playback()
            return
        total = self._loader.get_frame_count()
        next_frame = self._current_frame + 1
        if next_frame >= total:
            next_frame = 0
        self._current_frame = next_frame
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(next_frame)
        self.frame_slider.blockSignals(False)
        self._show_frame(next_frame)

    def _on_speed_changed(self, text: str):
        speed_map = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0, "8x": 8.0}
        self._playback_speed = speed_map.get(text, 1.0)
        if self._playing:
            interval_ms = max(30, int(500 / self._playback_speed))
            self._play_timer.start(interval_ms)

    def _on_colormap_changed(self, scheme: str):
        self._colormap_scheme = scheme
        if self._loader:
            self._loader.set_colormap(self._temp_min, self._temp_max, scheme)
            self._show_frame(self._current_frame)

    def _on_recording_selected(self, index: int):
        if index < 0 or index >= len(self._recordings):
            return
        self._load_recording(self._recordings[index])

    # -- Comparison view --

    def _open_compare_dialog(self):
        """Open dialog to select which recordings to compare."""
        if not self._recordings:
            return

        dlg = CompareSelectDialog(self._recordings, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.selected_indices()
            if len(selected) < 2:
                return
            self._show_comparison(selected)

    def _show_comparison(self, indices: list[int]):
        """Show selected recordings side by side."""
        self._stop_playback()
        self._stop_compare_playback()
        self._clear_comparison()

        self.viewer_container.hide()
        self.empty_label.hide()

        max_frames = 0

        for i in indices:
            rec = self._recordings[i]
            try:
                dt = datetime.fromisoformat(rec.timestamp)
                title = f"{rec.repair_type.replace('_', ' ').title()}\n{dt.strftime('%Y-%m-%d %H:%M')}"
            except (ValueError, TypeError):
                title = rec.recording_id

            panel = ComparisonPanel()
            ok = panel.load_recording(
                rec.recording_path, self._panel_id, title,
                self._temp_min, self._temp_max, self._colormap_scheme
            )
            if ok:
                max_frames = max(max_frames, panel.get_frame_count())
            self._comparison_panels.append(panel)
            self.comparison_layout.addWidget(panel)

        # Set up synchronized slider
        self._compare_frame = 0
        self.compare_slider.setMaximum(max(0, max_frames - 1))
        self.compare_slider.setValue(0)
        self.compare_frame_label.setText(f"0 / {max_frames}")

        self.comparison_wrapper.show()

    def _clear_comparison(self):
        self._stop_compare_playback()
        for panel in self._comparison_panels:
            panel.close_loader()
            panel.setParent(None)
            panel.deleteLater()
        self._comparison_panels.clear()
        self.comparison_wrapper.hide()

    # -- Comparison playback --

    def _toggle_compare_play(self):
        if self._compare_playing:
            self._stop_compare_playback()
        else:
            self._start_compare_playback()

    def _start_compare_playback(self):
        if not self._comparison_panels:
            return
        self._compare_playing = True
        self.compare_play_btn.setText("Pause")
        speed_map = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0, "8x": 8.0}
        speed = speed_map.get(self.compare_speed_combo.currentText(), 1.0)
        interval_ms = max(30, int(500 / speed))
        self._compare_timer.start(interval_ms)

    def _stop_compare_playback(self):
        self._compare_playing = False
        self._compare_timer.stop()
        self.compare_play_btn.setText("Play All")

    def _advance_compare_frame(self):
        if not self._comparison_panels:
            self._stop_compare_playback()
            return

        max_frames = self.compare_slider.maximum() + 1
        next_frame = self._compare_frame + 1
        if next_frame >= max_frames:
            next_frame = 0

        self._compare_frame = next_frame
        self.compare_slider.blockSignals(True)
        self.compare_slider.setValue(next_frame)
        self.compare_slider.blockSignals(False)
        self._sync_compare_frames(next_frame)

    def _on_compare_slider_changed(self, value: int):
        self._compare_frame = value
        self._sync_compare_frames(value)

    def _sync_compare_frames(self, frame_index: int):
        """Set all comparison panels to the given frame index."""
        for panel in self._comparison_panels:
            panel.set_frame(frame_index)
        max_frames = self.compare_slider.maximum() + 1
        self.compare_frame_label.setText(f"{frame_index + 1} / {max_frames}")

    def _on_compare_speed_changed(self, text: str):
        if self._compare_playing:
            speed_map = {"0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0, "8x": 8.0}
            speed = speed_map.get(text, 1.0)
            interval_ms = max(30, int(500 / speed))
            self._compare_timer.start(interval_ms)

    # -- Cleanup --

    def clear(self):
        self._stop_playback()
        self._stop_compare_playback()
        self._clear_comparison()
        if self._loader:
            self._loader.close()
            self._loader = None
        self._recordings = []
        self.frame_display.clear_frame()
        self.original_display.clear_frame()
        self.temp_graph.clear_data()
        self.empty_label.show()
        self.viewer_container.hide()
        self.comparison_wrapper.hide()
        self.recording_selector_label.hide()
        self.recording_combo.hide()
        self.compare_btn.hide()
        self.warning_banner.hide()

    def apply_theme(self):
        t = current_theme()
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
        self.recording_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        self.stats_label.setStyleSheet(
            f"color: {t.text_primary}; background: {t.surface_bg}; "
            f"border: 1px solid {t.border}; border-radius: 4px; padding: 6px;"
        )
        self.original_frame_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
        self.corrected_frame_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
        self.temp_graph.update()
        for panel in self._comparison_panels:
            panel.apply_theme()
