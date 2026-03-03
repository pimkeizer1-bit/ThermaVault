"""Recording loader - loads thermal frames from NPZ files."""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import numpy as np
import cv2

from .colormap import ThermalColormap


@dataclass
class ROI:
    """Region of Interest defined by 4 corner points."""
    corners: list  # [[x,y], [x,y], [x,y], [x,y]]

    @property
    def is_valid(self) -> bool:
        return len(self.corners) == 4

    def to_numpy(self) -> np.ndarray:
        return np.array(self.corners, dtype=np.float32)


@dataclass
class POIData:
    """Point of Interest from recording metadata."""
    poi_id: str
    name: str
    roi_corners: list
    aspect_ratio: float
    rotation: int
    panel_id: Optional[str]
    color: tuple

    @property
    def roi(self) -> ROI:
        return ROI(corners=self.roi_corners)


@dataclass
class RecordingMetadata:
    """Parsed recording metadata."""
    name: str
    start_time: str
    duration_seconds: float
    frame_count: int
    interval_seconds: float
    temp_range_min: float
    temp_range_max: float
    scale_min: float
    scale_max: float
    has_roi: bool
    roi_corners: Optional[list]
    aspect_ratio: float
    pois: List[POIData]


class RecordingLoader:
    """Loads and provides access to thermal recording data."""

    def __init__(self, recording_path: str):
        self.path = Path(recording_path)
        self.metadata: Optional[RecordingMetadata] = None
        self._npz_data = None
        self._colormap: Optional[ThermalColormap] = None

    def load(self) -> bool:
        """Load metadata and NPZ data. Returns True if successful."""
        metadata_path = self.path / "metadata.json"
        frames_path = self.path / "frames.npz"

        if not metadata_path.exists() or not frames_path.exists():
            return False

        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            # Parse POIs
            pois = []
            for poi_data in meta.get('pois', []):
                pois.append(POIData(
                    poi_id=poi_data.get('poi_id', ''),
                    name=poi_data.get('name', ''),
                    roi_corners=poi_data.get('roi_corners', []),
                    aspect_ratio=poi_data.get('aspect_ratio', 2.0),
                    rotation=poi_data.get('rotation', 0),
                    panel_id=poi_data.get('panel_id'),
                    color=tuple(poi_data.get('color', (0, 255, 128))),
                ))

            self.metadata = RecordingMetadata(
                name=meta['name'],
                start_time=meta.get('start_time', ''),
                duration_seconds=meta.get('duration_seconds', 0),
                frame_count=meta.get('frame_count', 0),
                interval_seconds=meta.get('interval_seconds', 0),
                temp_range_min=meta.get('temp_range_min', 0),
                temp_range_max=meta.get('temp_range_max', 0),
                scale_min=meta.get('scale_min', 10),
                scale_max=meta.get('scale_max', 150),
                has_roi=meta.get('has_roi', False),
                roi_corners=meta.get('roi_corners'),
                aspect_ratio=meta.get('aspect_ratio', 2.0),
                pois=pois,
            )

            self._npz_data = np.load(str(frames_path))
            return True
        except Exception as e:
            print(f"Error loading recording: {e}")
            return False

    def set_colormap(self, temp_min: float, temp_max: float, scheme: str = "ironbow"):
        """Set the colormap with the given temperature range and scheme."""
        self._colormap = ThermalColormap(
            temp_min=temp_min,
            temp_max=temp_max,
            scheme=scheme,
        )

    def get_frame_count(self) -> int:
        if self._npz_data is None:
            return 0
        return self.metadata.frame_count if self.metadata else 0

    def get_timestamp(self, index: int) -> float:
        """Get timestamp in seconds for a frame."""
        if self._npz_data is None:
            return 0.0
        timestamps = self._npz_data.get('timestamps')
        if timestamps is not None and index < len(timestamps):
            return float(timestamps[index])
        return 0.0

    def get_raw_frame(self, index: int) -> Optional[np.ndarray]:
        """Get raw temperature frame."""
        if self._npz_data is None:
            return None
        key = f"frame_{index:04d}"
        if key in self._npz_data:
            return self._npz_data[key]
        return None

    def get_panel_raw_corrected(self, index: int, panel_id: str,
                                output_width: int = 400) -> Optional[np.ndarray]:
        """Get perspective-corrected raw temperature data for a panel."""
        raw = self.get_raw_frame(index)
        if raw is None or self.metadata is None:
            return None

        poi = self._find_poi(panel_id)
        if poi is None:
            return None

        return self._apply_perspective(raw, poi.roi, poi.aspect_ratio,
                                       poi.rotation, output_width)

    def colormap_apply(self, raw_frame: np.ndarray) -> Optional[np.ndarray]:
        """Apply the current colormap to a raw temperature frame."""
        if self._colormap is None:
            return None
        return self._colormap.apply(raw_frame)

    def get_panel_frame(self, index: int, panel_id: str,
                        output_width: int = 400) -> Optional[np.ndarray]:
        """Get perspective-corrected RGB frame for a specific panel.

        Returns RGB image (H, W, 3) uint8 showing just this panel's ROI.
        """
        corrected = self.get_panel_raw_corrected(index, panel_id, output_width)
        if corrected is None or self._colormap is None:
            return None

        return self._colormap.apply(corrected)

    def get_full_frame_rgb(self, index: int,
                           highlight_panel_id: str = None,
                           show_all_rois: bool = False) -> Optional[np.ndarray]:
        """Get full frame as RGB with colormap applied.

        If highlight_panel_id is given, draws the ROI outline for that panel.
        If show_all_rois is True, draws all ROI outlines.
        """
        raw = self.get_raw_frame(index)
        if raw is None or self._colormap is None:
            return None

        rgb = self._colormap.apply(raw)

        if self.metadata:
            if show_all_rois:
                rgb = self._draw_all_roi_overlays(rgb, highlight_panel_id)
            elif highlight_panel_id:
                rgb = self._draw_roi_overlay(rgb, highlight_panel_id)

        return rgb

    def _draw_roi_overlay(self, rgb: np.ndarray, panel_id: str) -> np.ndarray:
        """Draw the ROI polygon and label for a panel on an RGB frame."""
        result = rgb.copy()
        poi = self._find_poi(panel_id)
        if poi is None or not poi.roi.is_valid:
            return result

        pts = np.array(poi.roi_corners, dtype=np.int32)
        color = poi.color  # RGB tuple

        # Draw polygon outline
        cv2.polylines(result, [pts], isClosed=True, color=color, thickness=2)

        # Draw corner dots
        for corner in poi.roi_corners:
            cv2.circle(result, (int(corner[0]), int(corner[1])), 3, color, -1)

        # Draw label
        label = poi.name
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        text_size = cv2.getTextSize(label, font, font_scale, thickness)[0]

        # Position label above top-left corner
        tx = int(pts[0][0])
        ty = int(pts[0][1]) - 8
        if ty < text_size[1] + 4:
            ty = int(pts[0][1]) + text_size[1] + 8

        # Background for readability
        cv2.rectangle(result,
                      (tx - 2, ty - text_size[1] - 2),
                      (tx + text_size[0] + 2, ty + 2),
                      (0, 0, 0), -1)
        cv2.putText(result, label, (tx, ty), font, font_scale, color, thickness)

        return result

    def _draw_all_roi_overlays(self, rgb: np.ndarray,
                               highlight_panel_id: str = None) -> np.ndarray:
        """Draw ROI overlays for all POIs. The highlighted panel gets a thicker outline."""
        result = rgb.copy()
        h, w = result.shape[:2]

        # Draw non-current panels first (behind), then current panel on top
        sorted_pois = sorted(self.metadata.pois,
                             key=lambda p: p.panel_id == highlight_panel_id)

        for poi in sorted_pois:
            if not poi.roi.is_valid:
                continue

            pts = np.array(poi.roi_corners, dtype=np.int32)
            color = poi.color
            is_current = (poi.panel_id == highlight_panel_id)

            if is_current:
                # Current panel: thick outline, full label above top-left
                cv2.polylines(result, [pts], isClosed=True, color=color, thickness=2)
                for corner in poi.roi_corners:
                    cv2.circle(result, (int(corner[0]), int(corner[1])), 3, color, -1)

                label = poi.name
                font_scale = 0.4
                text_thickness = 1
                font = cv2.FONT_HERSHEY_SIMPLEX
                text_size = cv2.getTextSize(label, font, font_scale, text_thickness)[0]

                tx = int(pts[0][0])
                ty = int(pts[0][1]) - 8
                if ty < text_size[1] + 4:
                    ty = int(pts[0][1]) + text_size[1] + 8

                cv2.rectangle(result,
                              (tx - 2, ty - text_size[1] - 2),
                              (tx + text_size[0] + 2, ty + 2),
                              (0, 0, 0), -1)
                cv2.putText(result, label, (tx, ty), font, font_scale, color, text_thickness)
            else:
                # Other panels: thin dashed-like outline, small label at bottom-right
                cv2.polylines(result, [pts], isClosed=True, color=color, thickness=1)

                label = poi.name
                font_scale = 0.3
                text_thickness = 1
                font = cv2.FONT_HERSHEY_SIMPLEX
                text_size = cv2.getTextSize(label, font, font_scale, text_thickness)[0]

                # Position at bottom-right corner of the ROI bounding box
                br_x = int(max(p[0] for p in poi.roi_corners))
                br_y = int(max(p[1] for p in poi.roi_corners))
                tx = br_x - text_size[0]
                ty = br_y + text_size[1] + 6
                # Clamp within frame
                tx = max(2, min(tx, w - text_size[0] - 2))
                ty = min(ty, h - 4)

                cv2.rectangle(result,
                              (tx - 2, ty - text_size[1] - 2),
                              (tx + text_size[0] + 2, ty + 2),
                              (0, 0, 0), -1)
                cv2.putText(result, label, (tx, ty), font, font_scale, color, text_thickness)

        return result

    def get_frame_stats(self, index: int, panel_id: str = None) -> Dict[str, float]:
        """Get temperature statistics for a frame (optionally for a specific panel ROI)."""
        raw = self.get_raw_frame(index)
        if raw is None:
            return {}

        if panel_id and self.metadata:
            poi = self._find_poi(panel_id)
            if poi:
                corrected = self._apply_perspective(raw, poi.roi, poi.aspect_ratio,
                                                    poi.rotation, 400)
                if corrected is not None:
                    raw = corrected

        return {
            'min': float(np.min(raw)),
            'max': float(np.max(raw)),
            'avg': float(np.mean(raw)),
        }

    def _find_poi(self, panel_id: str) -> Optional[POIData]:
        """Find POI by panel_id."""
        if self.metadata is None:
            return None
        for poi in self.metadata.pois:
            if poi.panel_id == panel_id:
                return poi
        return None

    def _apply_perspective(self, frame: np.ndarray, roi: ROI,
                           aspect_ratio: float, rotation: int,
                           output_width: int) -> Optional[np.ndarray]:
        """Apply perspective correction to extract a panel ROI."""
        if not roi.is_valid:
            return None

        output_height = int(output_width / aspect_ratio)
        src = roi.to_numpy()
        dst = np.array([
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1]
        ], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(src, dst)
        corrected = cv2.warpPerspective(
            frame, matrix, (output_width, output_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0
        )

        if rotation == 90:
            corrected = cv2.rotate(corrected, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            corrected = cv2.rotate(corrected, cv2.ROTATE_180)
        elif rotation == 270:
            corrected = cv2.rotate(corrected, cv2.ROTATE_90_COUNTERCLOCKWISE)

        return corrected

    def get_all_frame_stats(self, panel_id: str = None) -> Dict[str, list]:
        """Get temperature stats for all frames (for temperature graph).

        Returns dict with 'mins', 'maxs', 'avgs', 'timestamps' lists.
        """
        if self._npz_data is None or self.metadata is None:
            return {}

        frame_count = self.get_frame_count()
        mins, maxs, avgs, timestamps = [], [], [], []

        poi = self._find_poi(panel_id) if panel_id else None

        for i in range(frame_count):
            raw = self.get_raw_frame(i)
            if raw is None:
                continue

            data = raw
            if poi:
                corrected = self._apply_perspective(
                    raw, poi.roi, poi.aspect_ratio, poi.rotation, 100
                )
                if corrected is not None:
                    data = corrected

            mins.append(float(np.min(data)))
            maxs.append(float(np.max(data)))
            avgs.append(float(np.mean(data)))
            timestamps.append(self.get_timestamp(i))

        return {'mins': mins, 'maxs': maxs, 'avgs': avgs, 'timestamps': timestamps}

    def find_panel_in_recording(self, panel_id: str) -> bool:
        """Check if a specific panel has a POI in this recording."""
        return self._find_poi(panel_id) is not None

    def close(self):
        """Release NPZ data."""
        if self._npz_data is not None:
            self._npz_data.close()
            self._npz_data = None
