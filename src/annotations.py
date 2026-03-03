"""Annotation models and persistence manager for field notes (photos + comments)."""

import json
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

import cv2
import numpy as np


@dataclass
class PhotoAnnotation:
    """A photo attached to a recording annotation."""
    id: str
    filename: str
    timestamp: str
    caption: str = ""
    source: str = "file"  # "file" or "webcam"
    original_path: Optional[str] = None


@dataclass
class CommentAnnotation:
    """A text comment attached to a recording annotation."""
    id: str
    timestamp: str
    text: str


@dataclass
class RecordingAnnotations:
    """All annotations for one recording of one panel."""
    panel_id: str
    recording_id: str
    created: str = ""
    modified: str = ""
    comments: List[CommentAnnotation] = field(default_factory=list)
    photos: List[PhotoAnnotation] = field(default_factory=list)


class AnnotationManager:
    """Reads and writes annotation data in panel_data/annotations/."""

    def __init__(self, data_root: str):
        self.root = Path(data_root) / "panel_data" / "annotations"

    def _annotation_dir(self, panel_id: str, recording_id: str) -> Path:
        return self.root / panel_id / recording_id

    def _photos_dir(self, panel_id: str, recording_id: str) -> Path:
        return self._annotation_dir(panel_id, recording_id) / "photos"

    def _json_path(self, panel_id: str, recording_id: str) -> Path:
        return self._annotation_dir(panel_id, recording_id) / "annotations.json"

    def load(self, panel_id: str, recording_id: str) -> RecordingAnnotations:
        """Load annotations for a specific panel+recording. Returns empty if none exist."""
        json_path = self._json_path(panel_id, recording_id)
        if not json_path.exists():
            now = datetime.now().isoformat()
            return RecordingAnnotations(
                panel_id=panel_id,
                recording_id=recording_id,
                created=now,
                modified=now,
            )
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            comments = [CommentAnnotation(**c) for c in data.get('comments', [])]
            photos = [PhotoAnnotation(**p) for p in data.get('photos', [])]
            return RecordingAnnotations(
                panel_id=data.get('panel_id', panel_id),
                recording_id=data.get('recording_id', recording_id),
                created=data.get('created', ''),
                modified=data.get('modified', ''),
                comments=comments,
                photos=photos,
            )
        except (json.JSONDecodeError, OSError, TypeError):
            return RecordingAnnotations(panel_id=panel_id, recording_id=recording_id)

    def save(self, annotations: RecordingAnnotations):
        """Persist annotations to disk."""
        annotations.modified = datetime.now().isoformat()
        if not annotations.created:
            annotations.created = annotations.modified

        ann_dir = self._annotation_dir(annotations.panel_id, annotations.recording_id)
        ann_dir.mkdir(parents=True, exist_ok=True)

        data = {
            'panel_id': annotations.panel_id,
            'recording_id': annotations.recording_id,
            'created': annotations.created,
            'modified': annotations.modified,
            'comments': [asdict(c) for c in annotations.comments],
            'photos': [asdict(p) for p in annotations.photos],
        }
        json_path = self._json_path(annotations.panel_id, annotations.recording_id)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_photo_from_file(self, panel_id: str, recording_id: str,
                            source_path: str, caption: str = "") -> PhotoAnnotation:
        """Copy a photo file into the annotations photos/ directory."""
        photos_dir = self._photos_dir(panel_id, recording_id)
        photos_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        photo_id = f"photo_{now.strftime('%Y%m%d_%H%M%S')}"
        ext = Path(source_path).suffix.lower() or ".jpg"
        filename = f"{photo_id}{ext}"
        dest = photos_dir / filename
        shutil.copy2(source_path, dest)

        return PhotoAnnotation(
            id=photo_id,
            filename=filename,
            timestamp=now.isoformat(),
            caption=caption,
            source="file",
            original_path=source_path,
        )

    def add_photo_from_webcam(self, panel_id: str, recording_id: str,
                              frame_bgr: np.ndarray, caption: str = "") -> PhotoAnnotation:
        """Save a webcam-captured BGR frame as a JPEG."""
        photos_dir = self._photos_dir(panel_id, recording_id)
        photos_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        photo_id = f"webcam_{now.strftime('%Y%m%d_%H%M%S')}"
        filename = f"{photo_id}.jpg"
        dest = photos_dir / filename
        cv2.imwrite(str(dest), frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])

        return PhotoAnnotation(
            id=photo_id,
            filename=filename,
            timestamp=now.isoformat(),
            caption=caption,
            source="webcam",
            original_path=None,
        )

    def get_photo_path(self, panel_id: str, recording_id: str, filename: str) -> Path:
        """Return the full path to a photo file."""
        return self._photos_dir(panel_id, recording_id) / filename

    def delete_photo(self, panel_id: str, recording_id: str, photo: PhotoAnnotation):
        """Delete a photo file from disk."""
        path = self.get_photo_path(panel_id, recording_id, photo.filename)
        if path.exists():
            path.unlink()

    def get_annotation_count(self, panel_id: str, recording_id: str) -> tuple:
        """Return (comment_count, photo_count) without loading full data."""
        json_path = self._json_path(panel_id, recording_id)
        if not json_path.exists():
            return (0, 0)
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return (len(data.get('comments', [])), len(data.get('photos', [])))
        except (json.JSONDecodeError, OSError):
            return (0, 0)

    def get_panel_annotation_summary(self, panel_id: str,
                                     recording_ids: list) -> Dict[str, tuple]:
        """For each recording_id, return (comment_count, photo_count)."""
        result = {}
        for rec_id in recording_ids:
            result[rec_id] = self.get_annotation_count(panel_id, rec_id)
        return result
