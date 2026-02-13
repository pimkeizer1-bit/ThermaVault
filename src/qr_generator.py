"""QR code generation for panels.

Uses the same format as ThermalPanel so QR codes are interchangeable.
"""

from pathlib import Path
from typing import Optional

import numpy as np

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from .models import PanelData


QR_HEADER = "[ThermalCam Panel]"


def format_panel_qr_text(panel: PanelData) -> str:
    """Format panel info as QR-encodable plain text.

    Uses the same format as ThermalPanel for compatibility.
    """
    lines = [QR_HEADER]
    lines.append(f"ID: {panel.panel_id}")
    lines.append(f"Name: {panel.name}")

    if panel.location:
        lines.append(f"Location: {panel.location}")
    if panel.manufacturer:
        lines.append(f"Manufacturer: {panel.manufacturer}")
    if panel.model:
        lines.append(f"Model: {panel.model}")
    if panel.serial_number:
        lines.append(f"S/N: {panel.serial_number}")
    if panel.rated_power and float(panel.rated_power) > 0:
        lines.append(f"Power: {float(panel.rated_power):.0f}W")
    if panel.installation_date:
        lines.append(f"Installed: {panel.installation_date}")

    return "\n".join(lines)


def generate_qr_image(text: str, size: int = 400) -> Optional[np.ndarray]:
    """Generate QR code as RGB numpy array.

    Returns (size, size, 3) uint8 array, or None if qrcode not installed.
    """
    if not HAS_QRCODE:
        return None

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)

    pil_img = qr.make_image(fill_color="black", back_color="white")
    pil_img = pil_img.convert("RGB").resize((size, size))
    return np.array(pil_img)


def save_qr_image(qr_rgb: np.ndarray, path: str) -> bool:
    """Save QR code to PNG file."""
    if HAS_CV2:
        bgr = cv2.cvtColor(qr_rgb, cv2.COLOR_RGB2BGR)
        return cv2.imwrite(str(path), bgr)
    else:
        # Fallback with PIL
        from PIL import Image
        img = Image.fromarray(qr_rgb)
        img.save(path)
        return True


def generate_panel_qr(panel: PanelData, output_dir: str) -> Optional[str]:
    """Generate and save a QR code for a panel.

    Saves to: output_dir/QR_{panel_id}.png

    Returns the file path if successful, None otherwise.
    """
    text = format_panel_qr_text(panel)
    qr_rgb = generate_qr_image(text)
    if qr_rgb is None:
        return None

    output_path = Path(output_dir) / f"QR_{panel.panel_id}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if save_qr_image(qr_rgb, str(output_path)):
        return str(output_path)
    return None
