"""QR code display tab with auto-generation and DYMO label printing."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QInputDialog, QDialog, QScrollArea, QCheckBox, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage

import numpy as np

from ..models import PanelData
from ..theme import current_theme
from ..qr_generator import format_panel_qr_text, generate_qr_image, save_qr_image

# Windows GDI printing for DYMO LabelWriter (bypasses Qt's broken QPrinter)
try:
    import win32print
    import win32ui
    import win32gui
    import win32con
    from PIL import ImageWin
    HAS_WIN32PRINT = True
except ImportError:
    HAS_WIN32PRINT = False


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

        self.print_btn = QPushButton("Print DYMO Label")
        self.print_btn.clicked.connect(self._print_dymo_label)
        self.print_btn.setFixedWidth(160)
        self.print_btn.setToolTip(
            "Print 2 QR codes on a DYMO 5XL label (54x102mm, #30323)"
        )
        self.print_btn.hide()
        btn_layout.addWidget(self.print_btn)

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
            self.print_btn.show()
            # Load into _qr_rgb for printing
            from PIL import Image
            pil_img = Image.open(qr_path).convert("RGB")
            self._qr_rgb = np.array(pil_img)
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
            self.print_btn.show()
        else:
            self.info_label.setText("Generated")
            self.save_btn.show()
            self.print_btn.show()

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
                self.print_btn.show()
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

    def _build_label_pil(self, img_w: int, img_h: int):
        """Build a label as a PIL Image at the exact printer pixel dimensions.

        Args:
            img_w: Printable width in pixels (from GetDeviceCaps HORZRES)
            img_h: Printable height in pixels (from GetDeviceCaps VERTRES)

        Returns:
            PIL.Image.Image — RGB label image ready for printing via ImageWin.Dib
        """
        from PIL import Image, ImageDraw, ImageFont

        label = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(label)

        qr_pil = Image.fromarray(self._qr_rgb).convert("RGB")

        # Panel text
        panel_text = self._panel.panel_id
        if self._panel.name and self._panel.name != self._panel.panel_id:
            panel_text = self._panel.name

        # Font — scale relative to shorter side
        short_side = min(img_w, img_h)
        font_size = max(12, int(short_side * 0.045))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "Xg", font=font)
        text_h = (bbox[3] - bbox[1]) + int(short_side * 0.01)

        margin = int(short_side * 0.03)

        if img_h >= img_w:
            # Portrait: 2 QR codes stacked vertically
            cell_h = img_h // 2
            qr_max = min(img_w - 2 * margin, cell_h - text_h - 2 * margin)
            qr_size = int(qr_max * 0.55)
            qr_resized = qr_pil.resize((qr_size, qr_size), Image.NEAREST)

            for row in range(2):
                cy = row * cell_h
                qr_x = (img_w - qr_size) // 2
                qr_y = cy + (cell_h - qr_size - text_h) // 2
                label.paste(qr_resized, (qr_x, qr_y))

                tw = draw.textbbox((0, 0), panel_text, font=font)
                tx = (img_w - (tw[2] - tw[0])) // 2
                ty = qr_y + qr_size + margin // 3
                draw.text((tx, ty), panel_text, fill="black", font=font)
        else:
            # Landscape: 2 QR codes side by side
            cell_w = img_w // 2
            qr_max = min(cell_w - 2 * margin, img_h - text_h - 2 * margin)
            qr_size = int(qr_max * 0.55)
            qr_resized = qr_pil.resize((qr_size, qr_size), Image.NEAREST)

            for col in range(2):
                cx = col * cell_w
                qr_x = cx + (cell_w - qr_size) // 2
                qr_y = (img_h - qr_size - text_h) // 2
                label.paste(qr_resized, (qr_x, qr_y))

                tw = draw.textbbox((0, 0), panel_text, font=font)
                tx = cx + (cell_w - (tw[2] - tw[0])) // 2
                ty = qr_y + qr_size + margin // 3
                draw.text((tx, ty), panel_text, fill="black", font=font)

        return label

    # DYMO label type for #30323 Shipping (54x102mm)
    DYMO_LABEL_NAME = "30323"

    def _find_dymo_printer(self) -> str | None:
        """Find a DYMO LabelWriter printer by name.

        Returns the printer name string, or None if not found.
        If multiple DYMO printers are found, shows a selection dialog.
        """
        if not HAS_WIN32PRINT:
            return None

        # Enumerate all local and connected printers
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        all_printers = [p[2] for p in win32print.EnumPrinters(flags)]

        # Filter for DYMO printers
        dymo_printers = [p for p in all_printers if "dymo" in p.lower()]

        if not dymo_printers:
            return None
        elif len(dymo_printers) == 1:
            return dymo_printers[0]
        else:
            # Multiple DYMO printers — let user pick
            choice, ok = QInputDialog.getItem(
                self, "Select DYMO Printer",
                "Multiple DYMO printers found. Select one:",
                dymo_printers, 0, False
            )
            return choice if ok else None

    # Label dimensions in 1/10 mm for DEVMODE
    DYMO_LABEL_WIDTH_10MM = 540    # 54.0mm
    DYMO_LABEL_LENGTH_10MM = 1020  # 102.0mm

    def _get_dymo_devmode(self, printer_name: str):
        """Get a DEVMODE configured for the correct DYMO label size.

        Searches the driver's supported paper sizes for one matching
        DYMO_LABEL_NAME (e.g., '30323') and sets explicit dimensions.
        """
        hprinter = win32print.OpenPrinter(printer_name)
        try:
            devmode = win32print.GetPrinter(hprinter, 2)['pDevMode']
            port = win32print.GetPrinter(hprinter, 2).get('pPortName', '')

            # Find the paper ID for our label type
            paper_ids = win32print.DeviceCapabilities(printer_name, port, 2)
            paper_names = win32print.DeviceCapabilities(printer_name, port, 16)

            for i in range(len(paper_ids)):
                if i < len(paper_names) and self.DYMO_LABEL_NAME in paper_names[i]:
                    devmode.PaperSize = paper_ids[i]
                    break

            # Explicitly set paper dimensions
            devmode.PaperWidth = self.DYMO_LABEL_WIDTH_10MM
            devmode.PaperLength = self.DYMO_LABEL_LENGTH_10MM

            # Set Fields bitmask so the driver respects our size settings
            DM_PAPERSIZE = 0x2
            DM_PAPERLENGTH = 0x4
            DM_PAPERWIDTH = 0x8
            devmode.Fields = devmode.Fields | DM_PAPERSIZE | DM_PAPERLENGTH | DM_PAPERWIDTH

            # Validate through the driver
            DM_IN_BUFFER = 8
            DM_OUT_BUFFER = 2
            win32print.DocumentProperties(
                0, hprinter, printer_name,
                devmode, devmode,
                DM_IN_BUFFER | DM_OUT_BUFFER,
            )

            return devmode
        finally:
            win32print.ClosePrinter(hprinter)

    def _print_dymo_label(self):
        """Print 2 QR codes on a DYMO 5XL label via Windows GDI.

        Uses win32print/win32ui instead of QPrinter to avoid Qt's
        known bug where pageRect returns double the actual label width
        for DYMO printers with custom paper sizes.
        """
        if self._panel is None:
            return

        if not HAS_WIN32PRINT:
            QMessageBox.warning(
                self, "Print Error",
                "Label printing requires the pywin32 package.\n"
                "Install with: pip install pywin32"
            )
            return

        # Ensure we have a QR image
        if not hasattr(self, '_qr_rgb') or self._qr_rgb is None:
            qr_text = format_panel_qr_text(self._panel)
            qr_rgb = generate_qr_image(qr_text, size=400)
            if qr_rgb is None:
                QMessageBox.warning(
                    self, "Print Error",
                    "Could not generate QR code for printing."
                )
                return
            self._qr_rgb = qr_rgb

        # Find DYMO printer
        printer_name = self._find_dymo_printer()
        if not printer_name:
            QMessageBox.warning(
                self, "Print Error",
                "No DYMO printer found.\n\n"
                "Check that the DYMO LabelWriter is connected\n"
                "and the DYMO Connect driver is installed."
            )
            return

        try:
            # Get DEVMODE configured for the correct label size (#30323)
            devmode = self._get_dymo_devmode(printer_name)

            # Create GDI device context WITH the DEVMODE applied
            # (win32gui.CreateDC passes DEVMODE directly to the driver,
            #  unlike win32ui.CreatePrinterDC which ignores it)
            raw_hdc = win32gui.CreateDC('WINSPOOL', printer_name, devmode)
            hdc = win32ui.CreateDCFromHandle(raw_hdc)

            # Query the REAL printable area (now correct for #30323 labels)
            width_px = hdc.GetDeviceCaps(win32con.HORZRES)
            height_px = hdc.GetDeviceCaps(win32con.VERTRES)

            # Build label image at the exact printer dimensions
            label_img = self._build_label_pil(width_px, height_px)

            # Print via GDI
            hdc.StartDoc("ThermaVault QR Label")
            hdc.StartPage()

            dib = ImageWin.Dib(label_img)
            dib.draw(hdc.GetHandleOutput(), (0, 0, width_px, height_px))

            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()

            self.info_label.setText(f"Label sent to {printer_name}")

        except Exception as e:
            QMessageBox.warning(
                self, "Print Error",
                f"Could not print to {printer_name}:\n{e}"
            )

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


class QRBatchPrintDialog(QDialog):
    """Dialog to select multiple panels and print their QR labels in one batch."""

    DYMO_LABEL_NAME = "30323"
    DYMO_LABEL_WIDTH_10MM = 540
    DYMO_LABEL_LENGTH_10MM = 1020

    def __init__(self, panels: list, qr_dir: str | None, parent=None):
        super().__init__(parent)
        self._panels = panels
        self._qr_dir = qr_dir
        self._checkboxes: dict = {}  # panel_id -> QCheckBox
        self.setWindowTitle("Print QR Labels")
        self.setMinimumWidth(420)
        self.setMinimumHeight(480)
        self._init_ui()

    def _init_ui(self):
        t = current_theme()
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Select panels to print QR labels for:"))

        # Select all / none row
        btn_row = QHBoxLayout()
        all_btn = QPushButton("Select All")
        all_btn.setFixedWidth(90)
        all_btn.clicked.connect(lambda: self._set_all(True))
        btn_row.addWidget(all_btn)

        none_btn = QPushButton("None")
        none_btn.setFixedWidth(70)
        none_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(none_btn)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        btn_row.addStretch()
        btn_row.addWidget(self._count_label)
        layout.addLayout(btn_row)

        # Scrollable panel list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(2)

        for panel in sorted(self._panels, key=lambda p: p.name.lower()):
            cb = QCheckBox(f"{panel.name}  ({panel.panel_id})")
            cb.setChecked(True)
            cb.toggled.connect(self._update_count)
            self._checkboxes[panel.panel_id] = cb
            container_layout.addWidget(cb)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # Print / Close buttons
        action_row = QHBoxLayout()
        action_row.addStretch()

        self._print_btn = QPushButton("Print Selected")
        self._print_btn.setDefault(True)
        self._print_btn.setFixedWidth(130)
        self._print_btn.clicked.connect(self._print_selected)
        action_row.addWidget(self._print_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.reject)
        action_row.addWidget(close_btn)

        layout.addLayout(action_row)
        self._update_count()

    def _set_all(self, checked: bool):
        for cb in self._checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._update_count()

    def _update_count(self):
        n = sum(1 for cb in self._checkboxes.values() if cb.isChecked())
        total = len(self._checkboxes)
        self._count_label.setText(f"{n} of {total} selected")
        self._print_btn.setEnabled(n > 0)

    def _get_selected_panels(self) -> list:
        id_to_panel = {p.panel_id: p for p in self._panels}
        return [id_to_panel[pid] for pid, cb in self._checkboxes.items()
                if cb.isChecked() and pid in id_to_panel]

    def _print_selected(self):
        selected = self._get_selected_panels()
        if not selected:
            return

        if not HAS_WIN32PRINT:
            QMessageBox.warning(
                self, "Print Error",
                "Label printing requires the pywin32 package.\n"
                "Install with: pip install pywin32"
            )
            return

        printer_name = self._find_dymo_printer()
        if not printer_name:
            QMessageBox.warning(
                self, "Print Error",
                "No DYMO printer found.\n\n"
                "Check that the DYMO LabelWriter is connected\n"
                "and the DYMO Connect driver is installed."
            )
            return

        self._print_btn.setEnabled(False)
        try:
            devmode = self._get_dymo_devmode(printer_name)
            raw_hdc = win32gui.CreateDC('WINSPOOL', printer_name, devmode)
            hdc = win32ui.CreateDCFromHandle(raw_hdc)
            width_px = hdc.GetDeviceCaps(win32con.HORZRES)
            height_px = hdc.GetDeviceCaps(win32con.VERTRES)

            hdc.StartDoc("ThermaVault QR Labels")

            failed = []
            for i, panel in enumerate(selected):
                self._status_label.setText(
                    f"Printing {i + 1}/{len(selected)}: {panel.name}..."
                )
                QApplication.processEvents()

                qr_text = format_panel_qr_text(panel)
                qr_rgb = generate_qr_image(qr_text, size=400)
                if qr_rgb is None:
                    failed.append(panel.name)
                    continue

                hdc.StartPage()
                label_img = self._build_label_pil(qr_rgb, panel, width_px, height_px)
                dib = ImageWin.Dib(label_img)
                dib.draw(hdc.GetHandleOutput(), (0, 0, width_px, height_px))
                hdc.EndPage()

            hdc.EndDoc()
            hdc.DeleteDC()

            msg = f"Printed {len(selected) - len(failed)} label(s) to {printer_name}"
            if failed:
                msg += f"\nFailed: {', '.join(failed)}"
            self._status_label.setText(msg)

        except Exception as e:
            QMessageBox.warning(self, "Print Error", f"Could not print:\n{e}")
            self._status_label.setText("Print failed.")
        finally:
            self._update_count()  # re-enables print button if selection > 0

    def _find_dymo_printer(self) -> str | None:
        if not HAS_WIN32PRINT:
            return None
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        all_printers = [p[2] for p in win32print.EnumPrinters(flags)]
        dymo_printers = [p for p in all_printers if "dymo" in p.lower()]
        if not dymo_printers:
            return None
        elif len(dymo_printers) == 1:
            return dymo_printers[0]
        else:
            choice, ok = QInputDialog.getItem(
                self, "Select DYMO Printer",
                "Multiple DYMO printers found. Select one:",
                dymo_printers, 0, False
            )
            return choice if ok else None

    def _get_dymo_devmode(self, printer_name: str):
        hprinter = win32print.OpenPrinter(printer_name)
        try:
            devmode = win32print.GetPrinter(hprinter, 2)['pDevMode']
            port = win32print.GetPrinter(hprinter, 2).get('pPortName', '')
            paper_ids = win32print.DeviceCapabilities(printer_name, port, 2)
            paper_names = win32print.DeviceCapabilities(printer_name, port, 16)
            for i in range(len(paper_ids)):
                if i < len(paper_names) and self.DYMO_LABEL_NAME in paper_names[i]:
                    devmode.PaperSize = paper_ids[i]
                    break
            devmode.PaperWidth = self.DYMO_LABEL_WIDTH_10MM
            devmode.PaperLength = self.DYMO_LABEL_LENGTH_10MM
            DM_PAPERSIZE = 0x2
            DM_PAPERLENGTH = 0x4
            DM_PAPERWIDTH = 0x8
            devmode.Fields = devmode.Fields | DM_PAPERSIZE | DM_PAPERLENGTH | DM_PAPERWIDTH
            DM_IN_BUFFER = 8
            DM_OUT_BUFFER = 2
            win32print.DocumentProperties(
                0, hprinter, printer_name, devmode, devmode,
                DM_IN_BUFFER | DM_OUT_BUFFER,
            )
            return devmode
        finally:
            win32print.ClosePrinter(hprinter)

    def _build_label_pil(self, qr_rgb: np.ndarray, panel: PanelData,
                         img_w: int, img_h: int):
        from PIL import Image, ImageDraw, ImageFont
        label = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(label)
        qr_pil = Image.fromarray(qr_rgb).convert("RGB")

        panel_text = panel.name if panel.name and panel.name != panel.panel_id else panel.panel_id

        short_side = min(img_w, img_h)
        font_size = max(12, int(short_side * 0.045))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "Xg", font=font)
        text_h = (bbox[3] - bbox[1]) + int(short_side * 0.01)
        margin = int(short_side * 0.03)

        if img_h >= img_w:
            cell_h = img_h // 2
            qr_max = min(img_w - 2 * margin, cell_h - text_h - 2 * margin)
            qr_size = int(qr_max * 0.55)
            qr_resized = qr_pil.resize((qr_size, qr_size), Image.NEAREST)
            for row in range(2):
                cy = row * cell_h
                qr_x = (img_w - qr_size) // 2
                qr_y = cy + (cell_h - qr_size - text_h) // 2
                label.paste(qr_resized, (qr_x, qr_y))
                tw = draw.textbbox((0, 0), panel_text, font=font)
                tx = (img_w - (tw[2] - tw[0])) // 2
                ty = qr_y + qr_size + margin // 3
                draw.text((tx, ty), panel_text, fill="black", font=font)
        else:
            cell_w = img_w // 2
            qr_max = min(cell_w - 2 * margin, img_h - text_h - 2 * margin)
            qr_size = int(qr_max * 0.55)
            qr_resized = qr_pil.resize((qr_size, qr_size), Image.NEAREST)
            for col in range(2):
                cx = col * cell_w
                qr_x = cx + (cell_w - qr_size) // 2
                qr_y = (img_h - qr_size - text_h) // 2
                label.paste(qr_resized, (qr_x, qr_y))
                tw = draw.textbbox((0, 0), panel_text, font=font)
                tx = cx + (cell_w - (tw[2] - tw[0])) // 2
                ty = qr_y + qr_size + margin // 3
                draw.text((tx, ty), panel_text, fill="black", font=font)

        return label
