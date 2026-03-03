"""Field Notes tab: photos and comments per recording."""

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QScrollArea, QFrame, QFileDialog, QMessageBox, QSplitter,
    QGridLayout, QDialog, QSizePolicy, QInputDialog, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QAction

from ..annotations import (
    AnnotationManager, RecordingAnnotations, CommentAnnotation, PhotoAnnotation
)
from ..theme import current_theme


def _recording_label(rec) -> str:
    try:
        dt = datetime.fromisoformat(rec.timestamp)
        return f"{dt.strftime('%Y-%m-%d %H:%M')} - {rec.repair_type.replace('_', ' ').title()}"
    except (ValueError, TypeError):
        return rec.recording_id


class CommentCard(QFrame):
    """Displays a single comment with delete control."""

    delete_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str)

    def __init__(self, comment: CommentAnnotation, parent=None):
        super().__init__(parent)
        self.comment = comment
        self._init_ui()

    def _init_ui(self):
        t = current_theme()
        self.setStyleSheet(
            f"CommentCard {{ background: {t.surface_bg}; border: 1px solid {t.border}; "
            f"border-radius: 6px; padding: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        # Header row: timestamp + buttons
        header = QHBoxLayout()
        try:
            dt = datetime.fromisoformat(self.comment.timestamp)
            ts_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            ts_str = self.comment.timestamp

        ts_label = QLabel(ts_str)
        ts_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        header.addWidget(ts_label)
        header.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedSize(50, 24)
        edit_btn.setStyleSheet(f"font-size: 10px; padding: 2px;")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.comment.id))
        header.addWidget(edit_btn)

        del_btn = QPushButton("Delete")
        del_btn.setFixedSize(50, 24)
        del_btn.setStyleSheet(f"font-size: 10px; padding: 2px; color: #ff6b6b;")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.comment.id))
        header.addWidget(del_btn)

        layout.addLayout(header)

        # Comment text
        text_label = QLabel(self.comment.text)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_label.setStyleSheet(f"color: {t.text_primary}; font-size: 12px;")
        layout.addWidget(text_label)

    def apply_theme(self):
        t = current_theme()
        self.setStyleSheet(
            f"CommentCard {{ background: {t.surface_bg}; border: 1px solid {t.border}; "
            f"border-radius: 6px; padding: 4px; }}"
        )


class PhotoThumbnail(QFrame):
    """Clickable photo thumbnail for the gallery grid."""

    clicked = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    THUMB_SIZE = 140

    def __init__(self, photo: PhotoAnnotation, photo_path: Path, parent=None):
        super().__init__(parent)
        self.photo = photo
        self.photo_path = photo_path
        self.setFixedSize(self.THUMB_SIZE + 10, self.THUMB_SIZE + 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()

    def _init_ui(self):
        t = current_theme()
        self.setStyleSheet(
            f"PhotoThumbnail {{ background: {t.surface_bg}; border: 1px solid {t.border}; "
            f"border-radius: 4px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Thumbnail image
        self.thumb_label = QLabel()
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)

        if self.photo_path.exists():
            pixmap = QPixmap(str(self.photo_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.THUMB_SIZE, self.THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.thumb_label.setPixmap(scaled)
            else:
                self.thumb_label.setText("Failed to load")
                self.thumb_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")
        else:
            self.thumb_label.setText("Missing")
            self.thumb_label.setStyleSheet(f"color: {t.text_muted}; font-size: 10px;")

        layout.addWidget(self.thumb_label)

        # Caption
        caption = self.photo.caption or self.photo.source
        caption_label = QLabel(caption)
        caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 9px;")
        caption_label.setMaximumWidth(self.THUMB_SIZE)
        layout.addWidget(caption_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.photo.id)

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        view_action = QAction("View Full Size", self)
        view_action.triggered.connect(lambda: self.clicked.emit(self.photo.id))
        menu.addAction(view_action)

        delete_action = QAction("Delete Photo", self)
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self.photo.id))
        menu.addAction(delete_action)

        menu.exec(event.globalPos())


class PhotoViewerDialog(QDialog):
    """Full-size photo viewer dialog."""

    def __init__(self, photo: PhotoAnnotation, photo_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(photo.caption or photo.filename)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Photo display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        pixmap = QPixmap(str(photo_path))
        if not pixmap.isNull():
            self._pixmap = pixmap
            self._update_display()
        else:
            self.image_label.setText("Could not load image")
            self._pixmap = None

        layout.addWidget(self.image_label, 1)

        # Info bar
        t = current_theme()
        info = QLabel(
            f"{photo.filename}  |  Source: {photo.source}  |  {photo.timestamp}"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        layout.addWidget(info)

        # Caption
        if photo.caption:
            caption_label = QLabel(photo.caption)
            caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption_label.setWordWrap(True)
            caption_label.setStyleSheet(f"color: {t.text_primary}; font-size: 12px;")
            layout.addWidget(caption_label)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _update_display(self):
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()


class FieldNotesWidget(QWidget):
    """Field Notes tab: comments and photos per recording."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager: AnnotationManager | None = None
        self._panel_id: str = ""
        self._recordings: list = []
        self._annotations: RecordingAnnotations | None = None
        self._comment_cards: list[CommentCard] = []
        self._photo_thumbs: list[PhotoThumbnail] = []
        self._init_ui()

    def set_annotation_manager(self, manager: AnnotationManager):
        self._manager = manager

    def set_panel_recordings(self, panel_id: str, recordings: list):
        """Called when a panel is selected."""
        self._panel_id = panel_id
        self._recordings = recordings
        self._annotations = None

        self.recording_combo.blockSignals(True)
        self.recording_combo.clear()

        if not recordings:
            self.empty_label.setText("No recordings for this panel")
            self.empty_label.show()
            self.content_splitter.hide()
            self.recording_combo.hide()
            self.recording_label.hide()
            return

        for rec in recordings:
            self.recording_combo.addItem(_recording_label(rec), rec.recording_id)

        self.recording_combo.blockSignals(False)
        self.recording_label.show()
        self.recording_combo.show()

        self.recording_combo.setCurrentIndex(0)
        self._on_recording_selected(0)

    def _init_ui(self):
        t = current_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Recording selector
        selector_bar = QHBoxLayout()
        self.recording_label = QLabel("Recording:")
        selector_bar.addWidget(self.recording_label)
        self.recording_combo = QComboBox()
        self.recording_combo.currentIndexChanged.connect(self._on_recording_selected)
        selector_bar.addWidget(self.recording_combo, 1)
        self.recording_label.hide()
        self.recording_combo.hide()
        layout.addLayout(selector_bar)

        # Empty state
        self.empty_label = QLabel("Select a panel to add field notes")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
        layout.addWidget(self.empty_label)

        # Content area (splitter between comments and photos)
        self.content_splitter = QSplitter(Qt.Orientation.Vertical)

        # === Comments section ===
        comments_widget = QWidget()
        comments_layout = QVBoxLayout(comments_widget)
        comments_layout.setContentsMargins(0, 0, 0, 0)
        comments_layout.setSpacing(4)

        comments_header = QHBoxLayout()
        header_label = QLabel("Comments")
        header_label.setStyleSheet(f"font-weight: bold; color: {t.text_primary}; font-size: 13px;")
        comments_header.addWidget(header_label)
        comments_header.addStretch()
        self.comments_count_label = QLabel("0 comments")
        self.comments_count_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        comments_header.addWidget(self.comments_count_label)
        comments_layout.addLayout(comments_header)

        # Scrollable comments list
        self.comments_scroll = QScrollArea()
        self.comments_scroll.setWidgetResizable(True)
        self.comments_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.comments_container = QWidget()
        self.comments_list_layout = QVBoxLayout(self.comments_container)
        self.comments_list_layout.setContentsMargins(0, 0, 0, 0)
        self.comments_list_layout.setSpacing(4)
        self.comments_list_layout.addStretch()

        self.comments_scroll.setWidget(self.comments_container)
        comments_layout.addWidget(self.comments_scroll, 1)

        # Add comment input
        add_comment_bar = QHBoxLayout()
        self.comment_input = QTextEdit()
        self.comment_input.setPlaceholderText("Write a comment...")
        self.comment_input.setMaximumHeight(60)
        self.comment_input.setStyleSheet(
            f"background-color: {t.surface_bg}; color: {t.text_primary}; "
            f"border: 1px solid {t.border}; border-radius: 4px; padding: 4px;"
        )
        add_comment_bar.addWidget(self.comment_input, 1)

        self.add_comment_btn = QPushButton("Add")
        self.add_comment_btn.setFixedSize(60, 40)
        self.add_comment_btn.clicked.connect(self._add_comment)
        add_comment_bar.addWidget(self.add_comment_btn)

        comments_layout.addLayout(add_comment_bar)

        self.content_splitter.addWidget(comments_widget)

        # === Photos section ===
        photos_widget = QWidget()
        photos_layout = QVBoxLayout(photos_widget)
        photos_layout.setContentsMargins(0, 0, 0, 0)
        photos_layout.setSpacing(4)

        photos_header = QHBoxLayout()
        photos_header_label = QLabel("Photos")
        photos_header_label.setStyleSheet(f"font-weight: bold; color: {t.text_primary}; font-size: 13px;")
        photos_header.addWidget(photos_header_label)
        photos_header.addStretch()
        self.photos_count_label = QLabel("0 photos")
        self.photos_count_label.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        photos_header.addWidget(self.photos_count_label)

        self.add_file_btn = QPushButton("Add from File...")
        self.add_file_btn.setFixedWidth(120)
        self.add_file_btn.clicked.connect(self._add_photo_from_file)
        photos_header.addWidget(self.add_file_btn)

        self.webcam_btn = QPushButton("Capture Webcam...")
        self.webcam_btn.setFixedWidth(140)
        self.webcam_btn.clicked.connect(self._capture_from_webcam)
        photos_header.addWidget(self.webcam_btn)

        photos_layout.addLayout(photos_header)

        # Scrollable photo gallery
        self.photos_scroll = QScrollArea()
        self.photos_scroll.setWidgetResizable(True)
        self.photos_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.photos_container = QWidget()
        self.photos_grid = QGridLayout(self.photos_container)
        self.photos_grid.setContentsMargins(0, 0, 0, 0)
        self.photos_grid.setSpacing(8)

        self.photos_scroll.setWidget(self.photos_container)
        photos_layout.addWidget(self.photos_scroll, 1)

        self.content_splitter.addWidget(photos_widget)

        layout.addWidget(self.content_splitter, 1)
        self.content_splitter.hide()

    def _on_recording_selected(self, index: int):
        if index < 0 or index >= len(self._recordings):
            return
        self._load_annotations()

    def _current_recording_id(self) -> str:
        idx = self.recording_combo.currentIndex()
        if 0 <= idx < len(self._recordings):
            return self._recordings[idx].recording_id
        return ""

    def _load_annotations(self):
        rec_id = self._current_recording_id()
        if not rec_id or not self._manager:
            self.empty_label.show()
            self.content_splitter.hide()
            return

        self._annotations = self._manager.load(self._panel_id, rec_id)
        self.empty_label.hide()
        self.content_splitter.show()
        self._refresh_comments()
        self._refresh_photo_gallery()

    def _refresh_comments(self):
        # Clear existing cards
        for card in self._comment_cards:
            card.setParent(None)
            card.deleteLater()
        self._comment_cards.clear()

        # Remove stretch
        while self.comments_list_layout.count():
            item = self.comments_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._annotations:
            for comment in self._annotations.comments:
                card = CommentCard(comment)
                card.edit_requested.connect(self._on_edit_comment)
                card.delete_requested.connect(self._on_delete_comment)
                self._comment_cards.append(card)
                self.comments_list_layout.addWidget(card)

        self.comments_list_layout.addStretch()

        count = len(self._annotations.comments) if self._annotations else 0
        self.comments_count_label.setText(f"{count} comment{'s' if count != 1 else ''}")

    def _refresh_photo_gallery(self):
        # Clear existing thumbnails
        for thumb in self._photo_thumbs:
            thumb.setParent(None)
            thumb.deleteLater()
        self._photo_thumbs.clear()

        # Clear grid
        while self.photos_grid.count():
            item = self.photos_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._annotations or not self._manager:
            self.photos_count_label.setText("0 photos")
            return

        rec_id = self._current_recording_id()
        cols = 4
        for i, photo in enumerate(self._annotations.photos):
            photo_path = self._manager.get_photo_path(self._panel_id, rec_id, photo.filename)
            thumb = PhotoThumbnail(photo, photo_path)
            thumb.clicked.connect(self._on_photo_clicked)
            thumb.delete_requested.connect(self._on_delete_photo)
            self._photo_thumbs.append(thumb)
            self.photos_grid.addWidget(thumb, i // cols, i % cols)

        count = len(self._annotations.photos)
        self.photos_count_label.setText(f"{count} photo{'s' if count != 1 else ''}")

    # -- Comment operations --

    def _add_comment(self):
        text = self.comment_input.toPlainText().strip()
        if not text or not self._annotations or not self._manager:
            return

        now = datetime.now()
        comment = CommentAnnotation(
            id=f"comment_{now.strftime('%Y%m%d_%H%M%S')}",
            timestamp=now.isoformat(),
            text=text,
        )
        self._annotations.comments.append(comment)
        self._manager.save(self._annotations)
        self.comment_input.clear()
        self._refresh_comments()

    def _on_edit_comment(self, comment_id: str):
        if not self._annotations:
            return

        for comment in self._annotations.comments:
            if comment.id == comment_id:
                new_text, ok = QInputDialog.getMultiLineText(
                    self, "Edit Comment", "Comment:", comment.text
                )
                if ok and new_text.strip():
                    comment.text = new_text.strip()
                    self._manager.save(self._annotations)
                    self._refresh_comments()
                break

    def _on_delete_comment(self, comment_id: str):
        if not self._annotations or not self._manager:
            return

        reply = QMessageBox.question(
            self, "Delete Comment",
            "Are you sure you want to delete this comment?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._annotations.comments = [
            c for c in self._annotations.comments if c.id != comment_id
        ]
        self._manager.save(self._annotations)
        self._refresh_comments()

    # -- Photo operations --

    def _add_photo_from_file(self):
        if not self._annotations or not self._manager:
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Photo(s)",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.tiff *.gif);;All Files (*)",
        )
        if not paths:
            return

        rec_id = self._current_recording_id()
        for path in paths:
            caption, ok = QInputDialog.getText(
                self, "Photo Caption",
                f"Caption for {Path(path).name} (optional):",
            )
            if not ok:
                continue

            photo = self._manager.add_photo_from_file(
                self._panel_id, rec_id, path, caption=caption
            )
            self._annotations.photos.append(photo)

        self._manager.save(self._annotations)
        self._refresh_photo_gallery()

    def _capture_from_webcam(self):
        if not self._annotations or not self._manager:
            return

        from .webcam_dialog import WebcamCaptureDialog

        dlg = WebcamCaptureDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            frame = dlg.get_captured_frame()
            if frame is not None:
                caption, ok = QInputDialog.getText(
                    self, "Photo Caption", "Caption for webcam photo (optional):"
                )
                if not ok:
                    return

                rec_id = self._current_recording_id()
                photo = self._manager.add_photo_from_webcam(
                    self._panel_id, rec_id, frame, caption=caption
                )
                self._annotations.photos.append(photo)
                self._manager.save(self._annotations)
                self._refresh_photo_gallery()

    def _on_photo_clicked(self, photo_id: str):
        if not self._annotations or not self._manager:
            return

        rec_id = self._current_recording_id()
        for photo in self._annotations.photos:
            if photo.id == photo_id:
                photo_path = self._manager.get_photo_path(
                    self._panel_id, rec_id, photo.filename
                )
                dlg = PhotoViewerDialog(photo, photo_path, parent=self)
                dlg.exec()
                break

    def _on_delete_photo(self, photo_id: str):
        if not self._annotations or not self._manager:
            return

        reply = QMessageBox.question(
            self, "Delete Photo",
            "Are you sure you want to delete this photo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        rec_id = self._current_recording_id()
        for photo in self._annotations.photos:
            if photo.id == photo_id:
                self._manager.delete_photo(self._panel_id, rec_id, photo)
                break

        self._annotations.photos = [
            p for p in self._annotations.photos if p.id != photo_id
        ]
        self._manager.save(self._annotations)
        self._refresh_photo_gallery()

    # -- Cleanup --

    def clear(self):
        self._panel_id = ""
        self._recordings = []
        self._annotations = None
        self.recording_combo.clear()
        self.recording_label.hide()
        self.recording_combo.hide()
        self.empty_label.show()
        self.content_splitter.hide()

        for card in self._comment_cards:
            card.deleteLater()
        self._comment_cards.clear()

        for thumb in self._photo_thumbs:
            thumb.deleteLater()
        self._photo_thumbs.clear()

    def apply_theme(self):
        t = current_theme()
        self.empty_label.setStyleSheet(f"color: {t.text_muted}; padding: 40px;")
        self.comment_input.setStyleSheet(
            f"background-color: {t.surface_bg}; color: {t.text_primary}; "
            f"border: 1px solid {t.border}; border-radius: 4px; padding: 4px;"
        )
        for card in self._comment_cards:
            card.apply_theme()
