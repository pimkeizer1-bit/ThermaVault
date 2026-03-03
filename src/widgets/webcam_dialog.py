"""Webcam capture dialog using cv2.VideoCapture and QTimer for live preview."""

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QComboBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap

from ..theme import current_theme


def _enumerate_cameras(max_check: int = 8) -> list[tuple[int, str]]:
    """Probe camera indices 0..max_check-1 and return list of (index, label)."""
    cameras = []
    for idx in range(max_check):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cameras.append((idx, f"Camera {idx} ({w}x{h})"))
            cap.release()
    return cameras


class WebcamCaptureDialog(QDialog):
    """Dialog that shows a live webcam preview and lets the user capture a frame."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Webcam Capture")
        self.setMinimumSize(660, 540)

        self._capture: cv2.VideoCapture | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)
        self._captured_frame: np.ndarray | None = None
        self._preview_active = False
        self._cameras: list[tuple[int, str]] = []

        self._init_ui()
        self._detect_cameras()

    def _init_ui(self):
        t = current_theme()

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Camera selector
        selector_bar = QHBoxLayout()
        selector_bar.setSpacing(6)

        cam_label = QLabel("Source:")
        cam_label.setStyleSheet(f"color: {t.text_primary}; font-size: 12px;")
        selector_bar.addWidget(cam_label)

        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(200)
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        selector_bar.addWidget(self.camera_combo, 1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(70)
        self.refresh_btn.clicked.connect(self._detect_cameras)
        selector_bar.addWidget(self.refresh_btn)

        layout.addLayout(selector_bar)

        # Preview display
        self.preview_label = QLabel("Detecting cameras...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setStyleSheet(
            f"background-color: {t.surface_bg}; border: 1px solid {t.border}; "
            f"border-radius: 4px; color: {t.text_muted};"
        )
        layout.addWidget(self.preview_label, 1)

        # Status
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Controls
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.capture_btn = QPushButton("Capture")
        self.capture_btn.setFixedWidth(100)
        self.capture_btn.clicked.connect(self._take_snapshot)
        controls.addWidget(self.capture_btn)

        self.retake_btn = QPushButton("Retake")
        self.retake_btn.setFixedWidth(100)
        self.retake_btn.clicked.connect(self._retake)
        self.retake_btn.hide()
        controls.addWidget(self.retake_btn)

        controls.addStretch()

        self.accept_btn = QPushButton("Accept")
        self.accept_btn.setFixedWidth(100)
        self.accept_btn.clicked.connect(self.accept)
        self.accept_btn.setStyleSheet(
            f"QPushButton {{ background-color: {t.accent_green}; color: white; "
            f"border: none; border-radius: 4px; padding: 6px 16px; }}"
        )
        self.accept_btn.hide()
        controls.addWidget(self.accept_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        controls.addWidget(cancel_btn)

        layout.addLayout(controls)

    def _detect_cameras(self):
        """Enumerate available cameras and populate the combo box."""
        self._stop_preview()
        self.preview_label.setText("Detecting cameras...")
        self.capture_btn.setEnabled(False)

        # Force UI repaint before blocking probe
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        self._cameras = _enumerate_cameras()

        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()

        if not self._cameras:
            self.preview_label.setText(
                "No webcam detected.\n\n"
                "Please connect a camera and click Refresh."
            )
            self.status_label.setText("No cameras found")
            self.camera_combo.addItem("No cameras found")
            self.camera_combo.setEnabled(False)
            self.camera_combo.blockSignals(False)
            return

        self.camera_combo.setEnabled(True)
        for idx, label in self._cameras:
            self.camera_combo.addItem(label, idx)

        self.camera_combo.blockSignals(False)
        self.camera_combo.setCurrentIndex(0)
        self._start_preview(self._cameras[0][0])

    def _on_camera_changed(self, combo_index: int):
        """Switch to the selected camera."""
        if combo_index < 0 or combo_index >= len(self._cameras):
            return

        # If a snapshot was taken, discard it first
        self._captured_frame = None
        self.capture_btn.show()
        self.retake_btn.hide()
        self.accept_btn.hide()

        cam_idx = self._cameras[combo_index][0]
        self._stop_preview()
        self._start_preview(cam_idx)

    def _stop_preview(self):
        """Stop timer and release current camera."""
        self._timer.stop()
        self._preview_active = False
        if self._capture:
            self._capture.release()
            self._capture = None

    def _start_preview(self, camera_index: int = 0):
        """Open webcam and start live preview."""
        self._capture = cv2.VideoCapture(camera_index)

        if not self._capture.isOpened():
            self.preview_label.setText(
                f"Could not open Camera {camera_index}.\n\n"
                "It may be in use by another application."
            )
            self.status_label.setText("Camera not available")
            self.capture_btn.setEnabled(False)
            return

        self._preview_active = True
        self.capture_btn.setEnabled(True)
        self.status_label.setText("Live preview - press Capture to take a photo")
        self._timer.start(33)  # ~30fps

    def _update_frame(self):
        """Read one frame from webcam and display it."""
        if self._capture is None or not self._capture.isOpened():
            self._timer.stop()
            self.status_label.setText("Camera disconnected")
            self.capture_btn.setEnabled(False)
            return

        ret, frame = self._capture.read()
        if not ret:
            return

        self._display_frame(frame)

    def _display_frame(self, frame_bgr: np.ndarray):
        """Convert a BGR frame to QPixmap and display it."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def _take_snapshot(self):
        """Freeze the current frame."""
        if self._capture is None or not self._capture.isOpened():
            return

        ret, frame = self._capture.read()
        if not ret:
            return

        self._captured_frame = frame
        self._timer.stop()
        self._preview_active = False

        self._display_frame(frame)
        self.status_label.setText("Photo captured! Accept or Retake.")

        self.capture_btn.hide()
        self.retake_btn.show()
        self.accept_btn.show()
        self.camera_combo.setEnabled(False)
        self.refresh_btn.setEnabled(False)

    def _retake(self):
        """Discard snapshot and resume live preview."""
        self._captured_frame = None
        self._preview_active = True
        self.status_label.setText("Live preview - press Capture to take a photo")

        self.capture_btn.show()
        self.retake_btn.hide()
        self.accept_btn.hide()
        self.camera_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)

        self._timer.start(33)

    def get_captured_frame(self) -> np.ndarray | None:
        """Return the captured BGR frame, or None if cancelled."""
        return self._captured_frame

    def closeEvent(self, event):
        self._timer.stop()
        if self._capture:
            self._capture.release()
        super().closeEvent(event)

    def reject(self):
        self._captured_frame = None
        self._timer.stop()
        if self._capture:
            self._capture.release()
        super().reject()

    def accept(self):
        self._timer.stop()
        if self._capture:
            self._capture.release()
        super().accept()
