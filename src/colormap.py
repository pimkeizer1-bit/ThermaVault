"""
Fixed Temperature Color Scale for thermal visualization.

Copied from ThermalPanel - provides consistent color mapping.
"""

import numpy as np
from typing import Tuple, List
from dataclasses import dataclass


@dataclass
class ColorStop:
    """A color stop in a gradient."""
    position: float  # 0.0 to 1.0
    color: Tuple[int, int, int]  # RGB


class ThermalColormap:
    """Fixed-range temperature to color converter using LUT."""

    SCHEMES = {
        "ironbow": [
            ColorStop(0.00, (0, 0, 0)),
            ColorStop(0.20, (32, 0, 128)),
            ColorStop(0.35, (128, 0, 128)),
            ColorStop(0.50, (255, 0, 0)),
            ColorStop(0.65, (255, 128, 0)),
            ColorStop(0.80, (255, 255, 0)),
            ColorStop(1.00, (255, 255, 255)),
        ],
        "rainbow": [
            ColorStop(0.00, (0, 0, 128)),
            ColorStop(0.25, (0, 255, 255)),
            ColorStop(0.50, (0, 255, 0)),
            ColorStop(0.75, (255, 255, 0)),
            ColorStop(1.00, (255, 0, 0)),
        ],
        "grayscale": [
            ColorStop(0.00, (0, 0, 0)),
            ColorStop(1.00, (255, 255, 255)),
        ],
        "hot": [
            ColorStop(0.00, (0, 0, 0)),
            ColorStop(0.33, (255, 0, 0)),
            ColorStop(0.66, (255, 255, 0)),
            ColorStop(1.00, (255, 255, 255)),
        ],
        "cool_warm": [
            ColorStop(0.00, (59, 158, 255)),
            ColorStop(0.25, (71, 212, 160)),
            ColorStop(0.50, (245, 200, 66)),
            ColorStop(0.75, (255, 107, 74)),
            ColorStop(1.00, (255, 51, 102)),
        ],
        "plasma": [
            ColorStop(0.00, (13, 8, 135)),
            ColorStop(0.25, (126, 3, 168)),
            ColorStop(0.50, (204, 71, 120)),
            ColorStop(0.75, (248, 149, 64)),
            ColorStop(1.00, (240, 249, 33)),
        ],
    }

    def __init__(self, temp_min: float = 10.0, temp_max: float = 150.0,
                 scheme: str = "ironbow"):
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.temp_range = temp_max - temp_min

        if scheme in self.SCHEMES:
            self.color_stops = self.SCHEMES[scheme]
        else:
            self.color_stops = self.SCHEMES["ironbow"]

        self._build_lut()

    def _build_lut(self, resolution: int = 4096):
        self.lut_resolution = resolution
        self.lut = np.zeros((resolution, 3), dtype=np.uint8)
        for i in range(resolution):
            t = i / (resolution - 1)
            self.lut[i] = self._interpolate_color(t)

    def _interpolate_color(self, t: float) -> Tuple[int, int, int]:
        t = max(0.0, min(1.0, t))
        lower = self.color_stops[0]
        upper = self.color_stops[-1]

        for i, stop in enumerate(self.color_stops[:-1]):
            if stop.position <= t <= self.color_stops[i + 1].position:
                lower = stop
                upper = self.color_stops[i + 1]
                break

        if upper.position == lower.position:
            return lower.color

        local_t = (t - lower.position) / (upper.position - lower.position)
        r = int(lower.color[0] + local_t * (upper.color[0] - lower.color[0]))
        g = int(lower.color[1] + local_t * (upper.color[1] - lower.color[1]))
        b = int(lower.color[2] + local_t * (upper.color[2] - lower.color[2]))
        return (r, g, b)

    def apply(self, temp_frame: np.ndarray) -> np.ndarray:
        """Convert temperature frame to RGB image (H, W, 3) uint8."""
        normalized = (temp_frame - self.temp_min) / self.temp_range
        normalized = np.clip(normalized, 0, 1)
        indices = (normalized * (self.lut_resolution - 1)).astype(np.int32)
        return self.lut[indices]

    def get_colorbar_image(self, width: int = 30, height: int = 256) -> np.ndarray:
        """Generate vertical colorbar image."""
        colors = self.lut[np.linspace(self.lut_resolution - 1, 0, height).astype(int)]
        colorbar = np.tile(colors[:, np.newaxis, :], (1, width, 1))
        return colorbar.astype(np.uint8)

    @classmethod
    def list_schemes(cls) -> List[str]:
        return list(cls.SCHEMES.keys())
