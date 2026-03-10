"""Data Manager tab: reclassify, delete, and generate reports for recordings."""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QDialog, QComboBox,
    QFormLayout, QFrame, QCheckBox, QListWidget, QListWidgetItem, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ..models import PanelData, RecordingData, ReportFile
from ..theme import current_theme, ThemeManager
from .recording_table import REPAIR_COLORS, REPAIR_COLORS_LIGHT, REPAIR_DISPLAY_NAMES

COLUMNS = ['', 'Date', 'Type', 'Repair #', 'Recording ID', 'Frames',
           'Report', 'Notes']

REPAIR_TYPES = ['initial', 'pre_repair', 'post_repair', 'check', 'internal']

REPAIR_LABELS = {
    'initial': 'Initial',
    'pre_repair': 'Pre Repair',
    'post_repair': 'Post Repair',
    'check': 'Check',
    'internal': 'Internal',
}


class ReclassifyDialog(QDialog):
    """Dialog for choosing a new repair_type."""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Reclassify {count} Recording(s)")
        self.setFixedSize(320, 150)

        layout = QVBoxLayout(self)

        info = QLabel(f"Reclassifying {count} recording(s).")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        self.type_combo = QComboBox()
        for rt in REPAIR_TYPES:
            self.type_combo.addItem(REPAIR_LABELS[rt], rt)
        form.addRow("New Type:", self.type_combo)

        layout.addLayout(form)

        self.note_label = QLabel(
            "Pre/Post Repair recordings will be auto-assigned a repair number."
        )
        self.note_label.setWordWrap(True)
        t = current_theme()
        self.note_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(self.note_label)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self.accept)
        buttons.addWidget(apply_btn)

        layout.addLayout(buttons)

    def get_repair_type(self) -> str:
        return self.type_combo.currentData()


class DataManagerWidget(QWidget):
    """Data Manager tab: reclassify, delete, and generate reports."""

    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._writer = None
        self._panel: PanelData | None = None
        self._all_panels: list[PanelData] = []
        self._reports: list[ReportFile] = []
        self._recordings: list[RecordingData] = []
        self._init_ui()

    def set_data_writer(self, writer):
        self._writer = writer

    def set_all_panels(self, panels: list[PanelData]):
        self._all_panels = panels

    def _init_ui(self):
        t = current_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Info banner
        self.banner = QFrame()
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        banner_icon = QLabel("Info")
        banner_icon.setStyleSheet("font-weight: bold; color: #4e8fff;")
        banner_layout.addWidget(banner_icon)
        banner_text = QLabel(
            "Changes here modify panels.json directly. "
            "A backup is created automatically before every change."
        )
        banner_text.setWordWrap(True)
        banner_text.setStyleSheet(f"color: {t.text_primary}; font-size: 11px;")
        banner_layout.addWidget(banner_text, 1)
        self.banner.setStyleSheet(
            f"QFrame {{ background: {t.surface_bg}; border: 1px solid #4e8fff; "
            f"border-radius: 6px; }}"
        )
        layout.addWidget(self.banner)

        # Empty state
        self.empty_label = QLabel("Select a panel to manage recordings")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
        layout.addWidget(self.empty_label)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        # Checkbox column narrow
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(0, 30)
        self.table.hide()
        layout.addWidget(self.table, 1)

        # Action buttons
        self.actions_frame = QFrame()
        actions_layout = QHBoxLayout(self.actions_frame)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)

        self.reclassify_btn = QPushButton("Reclassify Selected")
        self.reclassify_btn.clicked.connect(self._on_reclassify)
        actions_layout.addWidget(self.reclassify_btn)

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setStyleSheet("color: #ff6b6b;")
        self.delete_btn.clicked.connect(self._on_delete)
        actions_layout.addWidget(self.delete_btn)

        self.gen_report_btn = QPushButton("Generate Reports")
        self.gen_report_btn.clicked.connect(self._on_generate_reports)
        actions_layout.addWidget(self.gen_report_btn)

        self.restore_btn = QPushButton("Restore Hidden")
        self.restore_btn.setToolTip("Restore recordings that were removed from the database")
        self.restore_btn.clicked.connect(self._on_restore_hidden)
        actions_layout.addWidget(self.restore_btn)

        self.rename_btn = QPushButton("Rename Panel")
        self.rename_btn.setToolTip("Rename this panel in the database")
        self.rename_btn.clicked.connect(self._on_rename_panel)
        actions_layout.addWidget(self.rename_btn)

        self.merge_btn = QPushButton("Merge into...")
        self.merge_btn.setToolTip("Move all recordings from this panel into another panel and remove this one")
        self.merge_btn.clicked.connect(self._on_merge_panel)
        actions_layout.addWidget(self.merge_btn)

        actions_layout.addStretch()

        # Quick select buttons
        select_all_btn = QPushButton("All")
        select_all_btn.setFixedWidth(50)
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        actions_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("None")
        select_none_btn.setFixedWidth(50)
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        actions_layout.addWidget(select_none_btn)

        select_unknown_btn = QPushButton("Unknown Only")
        select_unknown_btn.setFixedWidth(100)
        select_unknown_btn.clicked.connect(self._select_unknown)
        actions_layout.addWidget(select_unknown_btn)

        self.actions_frame.hide()
        layout.addWidget(self.actions_frame)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def set_panel(self, panel: PanelData, reports: list[ReportFile]):
        """Populate the table with panel recordings."""
        self._panel = panel
        self._reports = reports
        self._recordings = list(panel.recordings)

        if not self._recordings:
            self.empty_label.setText("No recordings for this panel")
            self.empty_label.show()
            self.table.hide()
            self.actions_frame.hide()
            self.status_label.setText("")
            return

        self.empty_label.hide()
        self.table.show()
        self.actions_frame.show()
        self._populate_table()

        unknown_count = sum(
            1 for r in self._recordings
            if r.repair_type in ('unknown', '')
        )
        no_report_count = sum(
            1 for r in self._recordings
            if not self._has_report(r)
        )
        self.status_label.setText(
            f"{len(self._recordings)} recordings  |  "
            f"{unknown_count} unclassified  |  "
            f"{no_report_count} without reports"
        )

    def _populate_table(self):
        """Fill the table with recording data."""
        self.table.setRowCount(len(self._recordings))

        is_dark = ThemeManager.instance().is_dark
        colors = REPAIR_COLORS if is_dark else REPAIR_COLORS_LIGHT

        for row, rec in enumerate(self._recordings):
            # Checkbox - use actual QCheckBox widget for reliable single-click toggling
            cb = QCheckBox()
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, cb_container)

            # Date
            try:
                dt = datetime.fromisoformat(rec.timestamp)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_str = rec.timestamp or '-'
            self._set_cell(row, 1, date_str, rec.repair_type, colors)

            # Type
            display_type = REPAIR_DISPLAY_NAMES.get(rec.repair_type, rec.repair_type.replace('_', ' ').title() if rec.repair_type else 'Unknown')
            self._set_cell(row, 2, display_type, rec.repair_type, colors)

            # Repair #
            repair_str = str(rec.repair_number) if rec.repair_number is not None else '-'
            self._set_cell(row, 3, repair_str, rec.repair_type, colors)

            # Recording ID
            self._set_cell(row, 4, rec.recording_id, rec.repair_type, colors)

            # Frames
            self._set_cell(row, 5, str(rec.frame_count), rec.repair_type, colors)

            # Has Report
            has_report = self._has_report(rec)
            report_str = 'Yes' if has_report else '-'
            item = self._set_cell(row, 6, report_str, rec.repair_type, colors)
            if has_report:
                item.setForeground(QColor('#47d4a0'))

            # Notes
            notes_short = rec.notes.replace('\n', ' ')[:60] if rec.notes else '-'
            item = self._set_cell(row, 7, notes_short, rec.repair_type, colors)
            if rec.notes:
                item.setToolTip(rec.notes)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 30)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

    def _set_cell(self, row: int, col: int, text: str,
                  repair_type: str, colors: dict) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        bg_hex = colors.get(repair_type)
        if bg_hex:
            item.setBackground(QColor(bg_hex))
        self.table.setItem(row, col, item)
        return item

    def _has_report(self, rec: RecordingData) -> bool:
        """Check if any report file matches this recording."""
        for report in self._reports:
            # Match by timestamp in filename
            try:
                dt = datetime.fromisoformat(rec.timestamp)
                ts_str = dt.strftime('%Y%m%d_%H%M%S')
                if ts_str in report.filename:
                    return True
            except (ValueError, TypeError):
                pass
            # Fallback: match by recording_id
            if rec.recording_id in report.filename:
                return True
        return False

    def _get_selected_indices(self) -> list[int]:
        """Get row indices where checkbox is checked."""
        selected = []
        for row in range(self.table.rowCount()):
            cb = self._get_row_checkbox(row)
            if cb and cb.isChecked():
                selected.append(row)
        return selected

    def _get_row_checkbox(self, row: int) -> QCheckBox | None:
        """Get the QCheckBox widget for a table row."""
        container = self.table.cellWidget(row, 0)
        if container:
            cb = container.findChild(QCheckBox)
            return cb
        return None

    def _set_all_checked(self, checked: bool):
        for row in range(self.table.rowCount()):
            cb = self._get_row_checkbox(row)
            if cb:
                cb.setChecked(checked)

    def _select_unknown(self):
        """Select only recordings with unknown/empty repair_type."""
        for row in range(self.table.rowCount()):
            rec = self._recordings[row]
            is_unknown = rec.repair_type in ('unknown', '')
            cb = self._get_row_checkbox(row)
            if cb:
                cb.setChecked(is_unknown)

    # -- Actions --

    def _on_reclassify(self):
        selected = self._get_selected_indices()
        if not selected:
            QMessageBox.information(self, "No Selection",
                                    "Please check the recordings you want to reclassify.")
            return

        if not self._writer or not self._panel:
            return

        dlg = ReclassifyDialog(len(selected), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_type = dlg.get_repair_type()
        success_count = 0
        last_msg = ""

        for idx in selected:
            rec = self._recordings[idx]
            ok, msg = self._writer.reclassify_recording(
                self._panel.panel_id, rec.recording_id, new_type
            )
            if ok:
                success_count += 1
            last_msg = msg

        self.status_label.setText(
            f"Reclassified {success_count}/{len(selected)} recording(s) as "
            f"'{REPAIR_LABELS.get(new_type, new_type)}'"
        )
        self.data_changed.emit()

    def _on_delete(self):
        selected = self._get_selected_indices()
        if not selected:
            QMessageBox.information(self, "No Selection",
                                    "Please check the recordings you want to delete.")
            return

        if not self._writer or not self._panel:
            return

        # Confirmation dialog
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Delete Recordings")
        msg_box.setText(
            f"Are you sure you want to remove {len(selected)} recording(s) "
            f"from the database?"
        )
        msg_box.setInformativeText(
            "A backup of panels.json will be created before deletion."
        )

        delete_files_cb = QCheckBox("Also delete recording files from disk")
        msg_box.setCheckBox(delete_files_cb)

        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        if msg_box.exec() != QMessageBox.StandardButton.Yes:
            return

        delete_files = delete_files_cb.isChecked()

        recording_ids = [self._recordings[idx].recording_id for idx in selected]
        ok, msg = self._writer.delete_recordings(
            self._panel.panel_id, recording_ids, delete_files
        )

        self.status_label.setText(msg)
        self.data_changed.emit()

    def _on_generate_reports(self):
        selected = self._get_selected_indices()
        if not selected:
            QMessageBox.information(self, "No Selection",
                                    "Please check the recordings to generate reports for.")
            return

        if not self._writer or not self._panel:
            return

        # Filter to recordings without reports
        to_generate = []
        for idx in selected:
            rec = self._recordings[idx]
            if not self._has_report(rec):
                to_generate.append(rec)

        if not to_generate:
            QMessageBox.information(
                self, "Already Have Reports",
                "All selected recordings already have reports."
            )
            return

        success_count = 0
        for rec in to_generate:
            ok, msg = self._writer.generate_json_report(
                self._panel.panel_id, rec, self._panel
            )
            if ok:
                success_count += 1

        self.status_label.setText(
            f"Generated {success_count}/{len(to_generate)} report(s)"
        )
        self.data_changed.emit()

    def _on_restore_hidden(self):
        if not self._writer or not self._panel:
            return

        hidden = list(self._panel.hidden_recordings)
        if not hidden:
            QMessageBox.information(self, "No Hidden Recordings",
                                    "There are no hidden recordings to restore.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Restore Hidden Recordings")
        dlg.setMinimumSize(400, 300)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(
            f"{len(hidden)} recording(s) were removed from this panel.\n"
            "Select which ones to restore:"
        ))

        list_widget = QListWidget()
        for rid in hidden:
            item = QListWidgetItem(rid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            list_widget.addItem(item)
        layout.addWidget(list_widget, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        buttons.addWidget(cancel_btn)
        restore_btn = QPushButton("Restore Selected")
        restore_btn.setDefault(True)
        restore_btn.clicked.connect(dlg.accept)
        buttons.addWidget(restore_btn)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        to_restore = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                to_restore.append(item.text())

        if not to_restore:
            return

        ok, msg = self._writer.restore_recordings(
            self._panel.panel_id, to_restore
        )
        self.status_label.setText(msg)
        self.data_changed.emit()

    def _on_merge_panel(self):
        if not self._writer or not self._panel:
            return

        others = [p for p in self._all_panels if p.panel_id != self._panel.panel_id]
        if not others:
            QMessageBox.information(self, "No Other Panels",
                                    "There are no other panels to merge into.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Merge Panel")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(
            f"Move all recordings from <b>{self._panel.name}</b> into:"
        ))

        combo = QComboBox()
        for p in sorted(others, key=lambda x: x.name.lower()):
            combo.addItem(f"{p.name}  ({p.panel_id})", userData=p.panel_id)
        layout.addWidget(combo)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        buttons.addWidget(cancel_btn)
        ok_btn = QPushButton("Merge")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dlg.accept)
        buttons.addWidget(ok_btn)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        target_panel_id = combo.currentData()
        target_name = combo.currentText().split("  (")[0]

        reply = QMessageBox.question(
            self, "Confirm Merge",
            f"Merge all recordings from '{self._panel.name}' into '{target_name}'?\n\n"
            f"'{self._panel.name}' will be permanently removed from the database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok, msg = self._writer.merge_panels(self._panel.panel_id, target_panel_id)
        self.status_label.setText(msg)
        if ok:
            self.data_changed.emit()

    def _on_rename_panel(self):
        if not self._writer or not self._panel:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Rename Panel")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(f"Current name:  <b>{self._panel.name}</b>"))
        layout.addWidget(QLabel("New name:"))
        name_edit = QLineEdit(self._panel.name)
        name_edit.selectAll()
        layout.addWidget(name_edit)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        buttons.addWidget(cancel_btn)
        ok_btn = QPushButton("Rename")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dlg.accept)
        buttons.addWidget(ok_btn)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = name_edit.text().strip()
        if not new_name or new_name == self._panel.name:
            return

        ok, msg = self._writer.rename_panel(self._panel.panel_id, new_name)
        self.status_label.setText(msg)
        if ok:
            self.data_changed.emit()

    # -- Cleanup --

    def clear(self):
        self._panel = None
        self._reports = []
        self._recordings = []
        self.table.setRowCount(0)
        self.table.hide()
        self.actions_frame.hide()
        self.empty_label.show()
        self.status_label.setText("")

    def apply_theme(self):
        t = current_theme()
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
        self.status_label.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 11px;"
        )
        self.banner.setStyleSheet(
            f"QFrame {{ background: {t.surface_bg}; border: 1px solid #4e8fff; "
            f"border-radius: 6px; }}"
        )
        if self._panel and self._recordings:
            self._populate_table()
