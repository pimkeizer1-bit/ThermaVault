"""QR code display tab with auto-generation support."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage

import numpy as np

from ..models import PanelData
from ..theme import current_theme
from ..qr_generator import format_panel_qr_text, generate_qr_image, save_qr_image


class QRDisplayWidget(QWidget):
    """Displays a QR code image with auto-generation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panel: PanelData | None = None
        self._qr_path: str | None = None
        self._qr_dir: str | None = None  # QR codes directory in data folder
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(f"color: {current_theme().text_muted}; padding: 10px;")
        layout.addWidget(self.info_label)

        # QR text content display
        self.text_label = QLabel()
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setStyleSheet(
            f"color: {current_theme().text_secondary}; font-size: 11px; "
            f"font-family: monospace; padding: 8px;"
        )
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.generate_btn = QPushButton("Generate QR Code")
        self.generate_btn.clicked.connect(self._generate_qr)
        self.generate_btn.setFixedWidth(160)
        btn_layout.addWidget(self.generate_btn)

        self.save_btn = QPushButton("Save As...")
        self.save_btn.clicked.connect(self._save_qr)
        self.save_btn.setFixedWidth(100)
        self.save_btn.hide()
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def set_qr_data(self, panel: PanelData, qr_path: str | None, qr_dir: str | None):
        """Set panel data and existing QR path.

        Args:
            panel: Panel data for QR generation
            qr_path: Path to existing QR code PNG, or None
            qr_dir: Path to QR codes directory (for saving generated QR codes)
        """
        self._panel = panel
        self._qr_path = qr_path
        self._qr_dir = qr_dir

        # Show QR text content
        qr_text = format_panel_qr_text(panel)
        self.text_label.setText(qr_text)

        if qr_path and Path(qr_path).exists():
            self._show_qr_from_file(qr_path)
            self.generate_btn.setText("Regenerate QR Code")
            self.save_btn.show()
        else:
            # Auto-generate the QR code in memory for display
            self._generate_and_display(auto=True)

    def _show_qr_from_file(self, path: str):
        """Display QR code from a file."""
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                300, 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            self.info_label.setText(Path(path).name)

    def _show_qr_from_array(self, rgb: np.ndarray):
        """Display QR code from RGB numpy array."""
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            300, 300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def _generate_and_display(self, auto: bool = False):
        """Generate QR code and display it."""
        if self._panel is None:
            return

        qr_text = format_panel_qr_text(self._panel)
        qr_rgb = generate_qr_image(qr_text)

        if qr_rgb is None:
            self.image_label.clear()
            self.info_label.setText(
                "QR code generation requires the 'qrcode' package.\n"
                "Install with: pip install qrcode[pil]"
            )
            self.generate_btn.hide()
            return

        self._qr_rgb = qr_rgb
        self._show_qr_from_array(np.ascontiguousarray(qr_rgb))

        if auto:
            self.info_label.setText("Generated (not saved yet)")
            self.generate_btn.setText("Save to Data Folder")
            self.save_btn.show()
        else:
            self.info_label.setText("Generated")
            self.save_btn.show()

    def _generate_qr(self):
        """Generate and save QR code to the data folder."""
        if self._panel is None:
            return

        qr_text = format_panel_qr_text(self._panel)
        qr_rgb = generate_qr_image(qr_text)
        if qr_rgb is None:
            return

        self._qr_rgb = qr_rgb

        # Save to QR codes directory if available
        if self._qr_dir:
            qr_dir = Path(self._qr_dir)
            qr_dir.mkdir(parents=True, exist_ok=True)
            save_path = qr_dir / f"QR_{self._panel.panel_id}.png"
            if save_qr_image(qr_rgb, str(save_path)):
                self._qr_path = str(save_path)
                self._show_qr_from_file(str(save_path))
                self.info_label.setText(f"Saved: {save_path.name}")
                self.generate_btn.setText("Regenerate QR Code")
                self.save_btn.show()
                return

        # Fallback: just display in memory
        self._generate_and_display()

    def _save_qr(self):
        """Save QR code to a user-chosen location."""
        if not hasattr(self, '_qr_rgb') or self._qr_rgb is None:
            return

        default_name = f"QR_{self._panel.panel_id}.png" if self._panel else "qr_code.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save QR Code", default_name, "PNG Images (*.png)"
        )
        if path:
            if save_qr_image(self._qr_rgb, path):
                self.info_label.setText(f"Saved to: {Path(path).name}")
            else:
                QMessageBox.warning(self, "Save Error", "Could not save QR code image.")

    def set_qr_path(self, path: str | None):
        """Legacy method - show QR from path only (no panel data)."""
        if path and Path(path).exists():
            self._show_qr_from_file(path)
            self.generate_btn.hide()
            self.save_btn.hide()
            self.text_label.hide()
        else:
            self.image_label.clear()
            self.image_label.setText("")
            self.info_label.setText("No QR code available for this panel")
            self.generate_btn.hide()
            self.save_btn.hide()
            self.text_label.hide()

    def apply_theme(self):
        t = current_theme()
        self.info_label.setStyleSheet(f"color: {t.text_muted}; padding: 10px;")
        self.text_label.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 11px; "
            f"font-family: monospace; padding: 8px;"
        )
