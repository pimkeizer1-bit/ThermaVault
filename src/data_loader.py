"""Read-only data loader for ThermalPanel data folders."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .models import PanelData, RecordingData, ReportFile, RepairEvent
from .utils.file_matching import parse_report_filename, parse_qr_filename


class DataLoader:
    """Loads and cross-references all ThermalPanel data (read-only)."""

    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self.panels_file = self.root / "panel_data" / "panels.json"
        self.reports_dir = self.root / "reports"
        self.recordings_dir = self.root / "recordings"
        self.qr_dir = self.root / "QR codes"

        self.panels: Dict[str, PanelData] = {}
        self.panel_reports: Dict[str, List[ReportFile]] = {}
        self.panel_qr_paths: Dict[str, str] = {}

        # Reverse lookup: panel name -> panel_id
        self._name_to_id: Dict[str, str] = {}

    def validate_root(self) -> Tuple[bool, str]:
        """Check if root path contains valid ThermalPanel data."""
        if not self.root.exists():
            return False, f"Path does not exist: {self.root}"
        if not self.panels_file.exists():
            return False, f"panels.json not found at: {self.panels_file}"
        try:
            with open(self.panels_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if 'panels' not in data:
                return False, "panels.json is missing 'panels' key"
        except json.JSONDecodeError as e:
            return False, f"panels.json is not valid JSON: {e}"
        return True, "OK"

    def load_all(self) -> Tuple[bool, str]:
        """Load panels.json + scan recordings + scan reports + scan QR codes.

        Returns (success, message).
        """
        valid, msg = self.validate_root()
        if not valid:
            return False, msg

        try:
            self._load_panels()
            self._discover_recordings()
            self._scan_reports()
            self._scan_qr_codes()
            return True, f"Loaded {len(self.panels)} panels"
        except Exception as e:
            return False, f"Error loading data: {e}"

    def _load_panels(self):
        """Parse panels.json into PanelData objects."""
        with open(self.panels_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.panels = {}
        self._name_to_id = {}

        for panel_id, panel_data in data.get('panels', {}).items():
            recordings = []
            for rec_data in panel_data.get('recordings', []):
                recordings.append(RecordingData(**rec_data))
            panel_data['recordings'] = recordings
            panel = PanelData(**panel_data)
            self.panels[panel_id] = panel
            self._name_to_id[panel.name.lower()] = panel_id

    def _discover_recordings(self):
        """Scan recording folders on disk and link any unlinked recordings to panels.

        panels.json only lists recordings that were explicitly saved via reports.
        This method scans all recording metadata to discover recordings that
        contain a panel's POI but aren't listed in its recordings array.
        """
        if not self.recordings_dir.exists():
            return

        # Build a set of (panel_id, recording_id) pairs already known
        known_links = set()
        for panel in self.panels.values():
            for rec in panel.recordings:
                known_links.add((panel.panel_id, rec.recording_id))

        # Scan all recording folders
        for rec_folder in sorted(self.recordings_dir.iterdir()):
            if not rec_folder.is_dir():
                continue
            meta_path = rec_folder / "metadata.json"
            frames_path = rec_folder / "frames.npz"
            if not meta_path.exists() or not frames_path.exists():
                continue

            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            recording_id = rec_folder.name
            pois = meta.get('pois', [])

            for poi in pois:
                panel_id = poi.get('panel_id')
                if not panel_id or panel_id not in self.panels:
                    continue

                if (panel_id, recording_id) in known_links:
                    continue

                # This recording contains the panel but isn't linked - add it
                discovered = RecordingData(
                    recording_id=recording_id,
                    recording_path=str(rec_folder),
                    timestamp=meta.get('start_time', ''),
                    duration=meta.get('duration_seconds', 0),
                    frame_count=meta.get('frame_count', 0),
                    temp_min=meta.get('temp_range_min', 0),
                    temp_max=meta.get('temp_range_max', 0),
                    temp_avg=(meta.get('temp_range_min', 0) + meta.get('temp_range_max', 0)) / 2,
                    notes="(discovered from recording metadata)",
                    repair_type="unknown",
                )
                self.panels[panel_id].recordings.append(discovered)
                known_links.add((panel_id, recording_id))

    def _scan_reports(self):
        """Scan reports/ folder, match files to panels."""
        self.panel_reports = {}

        if not self.reports_dir.exists():
            return

        # First pass: collect all report files
        report_files: Dict[str, ReportFile] = {}  # keyed by base name (without _data.json/.pdf)
        pdf_paths: Dict[str, str] = {}
        json_paths: Dict[str, str] = {}

        for file_path in self.reports_dir.iterdir():
            if not file_path.is_file():
                continue

            parsed = parse_report_filename(file_path.name)
            if parsed is None:
                continue

            panel_id, repair_type, timestamp_str = parsed
            is_pdf = file_path.name.endswith('.pdf')

            # Build a base key for companion matching
            base_key = f"{panel_id}_{repair_type}_{timestamp_str}"
            if is_pdf:
                pdf_paths[base_key] = str(file_path)
            else:
                json_paths[base_key] = str(file_path)

        # Second pass: create ReportFile objects with companion info
        all_base_keys = set(pdf_paths.keys()) | set(json_paths.keys())

        for base_key in all_base_keys:
            parts = base_key.split('_', 1)  # This won't work for complex IDs
            # Re-parse from actual files
            pdf_path = pdf_paths.get(base_key)
            json_path = json_paths.get(base_key)

            # Parse panel info from the base_key using the same logic
            # Find repair type keyword in base_key
            raw_panel_id = None
            repair_type = None
            timestamp_str = None
            for keyword in ['_pre_repair_', '_post_repair_', '_followup_', '_baseline_']:
                idx = base_key.rfind(keyword)
                if idx >= 0:
                    raw_panel_id = base_key[:idx]
                    repair_type = keyword.strip('_')
                    timestamp_str = base_key[idx + len(keyword):]
                    break

            if raw_panel_id is None:
                continue

            # Resolve to actual panel_id
            resolved_id = self._resolve_panel_id(raw_panel_id)

            if pdf_path:
                report = ReportFile(
                    file_path=pdf_path,
                    filename=Path(pdf_path).name,
                    panel_id=resolved_id,
                    repair_type=repair_type,
                    timestamp_str=timestamp_str,
                    is_pdf=True,
                    companion_path=json_path,
                )
                self.panel_reports.setdefault(resolved_id, []).append(report)

            if json_path:
                report = ReportFile(
                    file_path=json_path,
                    filename=Path(json_path).name,
                    panel_id=resolved_id,
                    repair_type=repair_type,
                    timestamp_str=timestamp_str,
                    is_pdf=False,
                    companion_path=pdf_path,
                )
                self.panel_reports.setdefault(resolved_id, []).append(report)

        # Sort reports by timestamp
        for panel_id in self.panel_reports:
            self.panel_reports[panel_id].sort(key=lambda r: r.timestamp_str)

    def _resolve_panel_id(self, raw_id: str) -> str:
        """Resolve a raw panel ID from a filename to an actual panel_id.

        Tries direct match first, then name-based matching.
        """
        if raw_id in self.panels:
            return raw_id
        # Try name-based match
        name_match = self._name_to_id.get(raw_id.lower())
        if name_match:
            return name_match
        return raw_id

    def _scan_qr_codes(self):
        """Scan QR codes/ folder for QR_<panel_id>.png files."""
        self.panel_qr_paths = {}

        if not self.qr_dir.exists():
            return

        for file_path in self.qr_dir.iterdir():
            if not file_path.is_file():
                continue
            panel_id = parse_qr_filename(file_path.name)
            if panel_id:
                resolved = self._resolve_panel_id(panel_id)
                self.panel_qr_paths[resolved] = str(file_path)

    def get_panel(self, panel_id: str) -> Optional[PanelData]:
        return self.panels.get(panel_id)

    def get_all_panels(self) -> List[PanelData]:
        return list(self.panels.values())

    def get_reports(self, panel_id: str) -> List[ReportFile]:
        return self.panel_reports.get(panel_id, [])

    def get_qr_path(self, panel_id: str) -> Optional[str]:
        return self.panel_qr_paths.get(panel_id)

    def search_panels(self, query: str) -> List[PanelData]:
        """Search panels by name, panel_id, location, or tags."""
        query = query.lower()
        results = []
        for panel in self.panels.values():
            if (query in panel.name.lower() or
                query in panel.panel_id.lower() or
                query in panel.location.lower() or
                any(query in tag.lower() for tag in panel.tags)):
                results.append(panel)
        return results

    def get_repair_history(self, panel_id: str) -> List[RepairEvent]:
        """Build repair event list for timeline display."""
        panel = self.panels.get(panel_id)
        if panel is None:
            return []

        recordings = sorted(panel.recordings, key=lambda r: r.timestamp)
        repair_groups: Dict[int, RepairEvent] = {}

        for rec in recordings:
            if rec.repair_number is not None:
                if rec.repair_number not in repair_groups:
                    repair_groups[rec.repair_number] = RepairEvent(
                        repair_number=rec.repair_number
                    )
                event = repair_groups[rec.repair_number]
                if rec.repair_type == "pre_repair":
                    event.pre_repair = rec
                elif rec.repair_type == "post_repair":
                    event.post_repair = rec

        events = []
        for repair_num in sorted(repair_groups.keys()):
            event = repair_groups[repair_num]
            if event.pre_repair and event.post_repair:
                event.temp_improvement = (
                    event.pre_repair.temp_avg - event.post_repair.temp_avg
                )
            events.append(event)

        return events

    def get_panel_summary(self, panel_id: str) -> Dict[str, Any]:
        """Get summary statistics for a panel."""
        panel = self.panels.get(panel_id)
        if panel is None or not panel.recordings:
            return {}

        recordings = sorted(panel.recordings, key=lambda r: r.timestamp)

        baseline = None
        for rec in recordings:
            if rec.repair_type == "baseline":
                baseline = rec
                break
        if baseline is None:
            baseline = recordings[0]

        latest = recordings[-1]

        return {
            'total_recordings': len(recordings),
            'first_recording_date': recordings[0].timestamp,
            'last_recording_date': recordings[-1].timestamp,
            'baseline_temp_avg': baseline.temp_avg,
            'latest_temp_avg': latest.temp_avg,
            'temp_trend': latest.temp_avg - baseline.temp_avg,
        }
