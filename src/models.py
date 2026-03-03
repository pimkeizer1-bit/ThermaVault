"""Data models for ThermaVault (read-only)."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RecordingData:
    """A recording entry from panels.json."""
    recording_id: str
    recording_path: str
    timestamp: str
    duration: float
    frame_count: int
    temp_min: float
    temp_max: float
    temp_avg: float
    notes: str = ""
    repair_type: str = ""
    repair_number: Optional[int] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class PanelData:
    """Panel data from panels.json."""
    panel_id: str
    name: str
    location: str = ""
    installation_date: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    rated_power: float = 0.0
    notes: str = ""
    created_date: str = ""
    recordings: List[RecordingData] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    next_repair_number: int = 1
    hidden_recordings: List[str] = field(default_factory=list)


@dataclass
class ReportFile:
    """A report file found in the reports/ folder."""
    file_path: str
    filename: str
    panel_id: str
    repair_type: str
    timestamp_str: str
    is_pdf: bool
    companion_path: Optional[str] = None


@dataclass
class RepairEvent:
    """A repair event for timeline display."""
    repair_number: int
    pre_repair: Optional[RecordingData] = None
    post_repair: Optional[RecordingData] = None
    temp_improvement: Optional[float] = None
