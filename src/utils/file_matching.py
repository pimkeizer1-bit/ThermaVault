"""Report and QR code filename parsing and panel matching."""

from typing import Optional, Tuple

# Repair type keywords that appear in report filenames
REPAIR_KEYWORDS = ['_pre_repair_', '_post_repair_', '_followup_', '_baseline_']


def parse_report_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """Extract (panel_id, repair_type, timestamp_str) from a report filename.

    Handles patterns like:
        haddy_panel_002_baseline_20260212_153731.pdf
        haddy_panel_005_pre_repair_20260211_181055_data.json

    Returns None if the filename doesn't match the expected pattern.
    """
    name = filename

    # Determine file type and strip extension
    is_data_json = name.endswith('_data.json')
    if is_data_json:
        name = name[:-10]  # strip '_data.json'
    elif name.endswith('.pdf'):
        name = name[:-4]   # strip '.pdf'
    else:
        return None

    # Find the repair type keyword using rfind (handles panel_ids with underscores)
    for keyword in REPAIR_KEYWORDS:
        idx = name.rfind(keyword)
        if idx >= 0:
            panel_id = name[:idx]
            repair_type = keyword.strip('_')
            timestamp_str = name[idx + len(keyword):]
            return (panel_id, repair_type, timestamp_str)

    return None


def parse_qr_filename(filename: str) -> Optional[str]:
    """Extract panel_id from a QR code filename.

    Pattern: QR_{panel_id}.png
    Returns panel_id or None.
    """
    if filename.startswith('QR_') and filename.lower().endswith('.png'):
        return filename[3:-4]  # strip 'QR_' and '.png'
    return None
