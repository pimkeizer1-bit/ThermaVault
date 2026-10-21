"""Dialog for exporting a portable package (app + data) as a zip file."""

import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QProgressBar, QFileDialog, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal

from ..exporter import app_folder, collect_files, export_package


class _ExportWorker(QThread):
    progress = pyqtSignal(int, int, str)  # bytes_done, bytes_total, current file
    done = pyqtSignal(bool, str)

    def __init__(self, data_root: str, dest: str, include_app: bool,
                 include_capture_app: bool):
        super().__init__()
        self._args = (data_root, dest, include_app, include_capture_app)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        ok, msg = export_package(
            *self._args,
            progress=lambda d, t, f: self.progress.emit(d, t, f),
            is_cancelled=lambda: self._cancelled,
        )
        self.done.emit(ok, msg)


class ExportPackageDialog(QDialog):
    """Pick a destination and options, then write the export zip."""

    def __init__(self, data_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Package")
        self.setMinimumWidth(560)
        self._data_root = data_root
        self._worker = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Creates one zip file with everything needed to continue on another PC: "
            "all panels, recordings (video frames), reports, annotations and photos. "
            "Unzip it anywhere and run ThermaVault.exe."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel(f"Data folder:  {data_root}"))

        dest_row = QHBoxLayout()
        default_name = f"ThermaVault_export_{datetime.now():%Y-%m-%d}.zip"
        self.dest_edit = QLineEdit(str(Path(data_root).parent / default_name))
        dest_row.addWidget(self.dest_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        dest_row.addWidget(browse_btn)
        layout.addLayout(dest_row)

        self.app_check = QCheckBox("Include the ThermaVault app (ready to run)")
        if app_folder() is None:
            self.app_check.setEnabled(False)
            self.app_check.setToolTip("Only available in the portable build (ThermaVault.exe)")
        else:
            self.app_check.setChecked(True)
        layout.addWidget(self.app_check)

        self.capture_check = QCheckBox("Include the ThermalPanel capture app")
        self.capture_check.setChecked(True)
        layout.addWidget(self.capture_check)

        self.size_label = QLabel("")
        layout.addWidget(self.size_label)
        self.app_check.toggled.connect(self._update_size)
        self.capture_check.toggled.connect(self._update_size)
        self._update_size()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._start)
        buttons.addWidget(self.export_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)

    def _total_bytes(self) -> int:
        files = collect_files(self._data_root, self.app_check.isChecked(),
                              self.capture_check.isChecked())
        return sum(p.stat().st_size for p, _ in files)

    def _update_size(self):
        self.size_label.setText(f"Estimated size: {self._total_bytes() / 1e6:,.0f} MB")

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Export Package", self.dest_edit.text(), "Zip files (*.zip)"
        )
        if path:
            self.dest_edit.setText(path)

    def _start(self):
        dest = Path(self.dest_edit.text().strip())
        if dest.suffix.lower() != '.zip':
            dest = dest.with_suffix('.zip')
        if not dest.parent.exists():
            QMessageBox.warning(self, "Export", f"Folder does not exist:\n{dest.parent}")
            return
        if dest.exists():
            reply = QMessageBox.question(
                self, "Export", f"{dest.name} already exists. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        needed = self._total_bytes()
        free = shutil.disk_usage(dest.parent).free
        if free < needed * 1.05:
            QMessageBox.warning(
                self, "Not Enough Space",
                f"The export needs about {needed / 1e6:,.0f} MB but only "
                f"{free / 1e6:,.0f} MB is free on that drive."
            )
            return

        self.dest_edit.setEnabled(False)
        self.app_check.setEnabled(False)
        self.capture_check.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.show()

        self._worker = _ExportWorker(self._data_root, str(dest),
                                     self.app_check.isChecked(),
                                     self.capture_check.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, done: int, total: int, current: str):
        self.progress_bar.setValue(int(done * 1000 / total) if total else 1000)
        self.status_label.setText(
            f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB   {current}"
        )

    def _on_done(self, ok: bool, msg: str):
        self._worker = None
        if ok:
            QMessageBox.information(self, "Export Complete", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Export", msg)
            self.reject()

    def _cancel(self):
        self.reject()

    def reject(self):
        # Escape / Cancel / close during an export: stop the worker first,
        # _on_done closes the dialog once the partial zip is removed.
        if self._worker is not None:
            self.status_label.setText("Cancelling...")
            self._worker.cancel()
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None:
            self.reject()
            event.ignore()
            return
        super().closeEvent(event)
