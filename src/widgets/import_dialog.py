"""Dialog for importing data from an Export Package zip or another data folder."""

import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QProgressBar, QFileDialog, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal

from ..data_writer import DataWriter
from ..importer import extract_package, find_data_folder


class _ImportWorker(QThread):
    progress = pyqtSignal(str, int, int, str)  # stage, bytes_done, bytes_total, current file
    done = pyqtSignal(bool, str)

    def __init__(self, writer: DataWriter, source: str):
        super().__init__()
        self._writer = writer
        self._source = source
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        tmp = None
        try:
            if Path(self._source).is_file():
                data_dir, tmp, err = extract_package(
                    self._source, str(self._writer.root),
                    progress=lambda d, t, f: self.progress.emit("Reading package", d, t, f),
                    is_cancelled=lambda: self._cancelled,
                )
                if data_dir is None:
                    self.done.emit(False, err)
                    return
            else:
                data_dir = find_data_folder(self._source)
                if data_dir is None:
                    self.done.emit(False, "No ThermalPanel data (panel_data/panels.json) "
                                          "found in that folder")
                    return
            # Past this point local data is being written: no more cancelling
            ok, msg = self._writer.import_from_folder(
                str(data_dir), copy_files=True,
                progress=lambda d, t, f: self.progress.emit("Copying", d, t, f),
            )
            self.done.emit(ok, msg)
        except Exception as e:
            self.done.emit(False, f"Import failed: {e}")
        finally:
            if tmp is not None:
                shutil.rmtree(tmp, ignore_errors=True)


class ImportDialog(QDialog):
    """Pick an Export Package zip or a data folder, then merge it into the open data."""

    def __init__(self, writer: DataWriter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Data")
        self.setMinimumWidth(560)
        self._writer = writer
        self._worker = None
        self.imported = False

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Adds what is missing from an Export Package (.zip) or another ThermalPanel "
            "data folder: panels, recordings, reports, field notes and photos, captures "
            "and QR codes. Nothing in your current data is overwritten; your repair "
            "types and hidden recordings are kept."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(QLabel(f"Import into:  {writer.root}"))

        src_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Export Package .zip or ThermalPanel folder")
        self.source_edit.textChanged.connect(self._update_buttons)
        src_row.addWidget(self.source_edit, 1)
        self.zip_btn = QPushButton("Zip...")
        self.zip_btn.clicked.connect(self._browse_zip)
        src_row.addWidget(self.zip_btn)
        self.folder_btn = QPushButton("Folder...")
        self.folder_btn.clicked.connect(self._browse_folder)
        src_row.addWidget(self.folder_btn)
        layout.addLayout(src_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.import_btn = QPushButton("Import")
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self._start)
        buttons.addWidget(self.import_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)
        self._update_buttons()

    def _update_buttons(self):
        self.import_btn.setEnabled(bool(self.source_edit.text().strip()))

    def _browse_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Export Package", "", "Zip files (*.zip)"
        )
        if path:
            self.source_edit.setText(path)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select ThermalPanel data folder to import from",
            "", QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.source_edit.setText(folder)

    def _start(self):
        source = Path(self.source_edit.text().strip().strip('"'))
        if not source.exists():
            QMessageBox.warning(self, "Import", f"Not found:\n{source}")
            return
        if source.is_dir():
            data_dir = find_data_folder(str(source))
            if data_dir is None:
                QMessageBox.warning(self, "Import",
                                    "No ThermalPanel data (panel_data/panels.json) "
                                    "found in that folder.")
                return
            if data_dir.resolve() == self._writer.root.resolve():
                QMessageBox.warning(self, "Import", "That is the data folder already open.")
                return
        elif source.suffix.lower() != '.zip':
            QMessageBox.warning(self, "Import", "Pick an Export Package .zip or a folder.")
            return

        self.source_edit.setEnabled(False)
        self.zip_btn.setEnabled(False)
        self.folder_btn.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.cancel_btn.setEnabled(source.is_file())
        self.progress_bar.show()
        self.status_label.setText("Scanning...")

        self._worker = _ImportWorker(self._writer, str(source))
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, stage: str, done: int, total: int, current: str):
        self.progress_bar.setValue(int(done * 1000 / total) if total else 1000)
        # Cancelling is only possible while the package is being read
        self.cancel_btn.setEnabled(stage == "Reading package")
        self.status_label.setText(
            f"{stage}: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB   {current}"
        )

    def _on_done(self, ok: bool, msg: str):
        self._worker = None
        if ok:
            self.imported = True
            QMessageBox.information(self, "Import Complete", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Import", msg)
            super().reject()

    def reject(self):
        # Escape / Cancel / close during an import: ask the worker to stop,
        # _on_done closes the dialog once it has finished or cleaned up.
        if self._worker is not None:
            if self.cancel_btn.isEnabled():
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
