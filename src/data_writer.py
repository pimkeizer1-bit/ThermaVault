"""Safe data mutations for panels.json with backup and atomic writes."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class DataWriter:
    """Handles all write operations to panels.json with automatic backups."""

    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self.panels_file = self.root / "panel_data" / "panels.json"
        self.backup_dir = self.root / "panel_data" / "backups"
        self.reports_dir = self.root / "reports"
        self.recordings_dir = self.root / "recordings"

    def _read_current(self) -> dict:
        """Read current panels.json from disk (always fresh)."""
        with open(self.panels_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _backup(self) -> str:
        """Create a timestamped backup of panels.json. Returns backup path."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.backup_dir / f"panels_backup_{timestamp}.json"
        shutil.copy2(str(self.panels_file), str(backup_path))
        return str(backup_path)

    def _write_atomic(self, data: dict):
        """Write data to panels.json atomically via temp file."""
        data['last_updated'] = datetime.now().isoformat()
        tmp_path = self.panels_file.with_suffix('.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(self.panels_file)

    def reclassify_recording(self, panel_id: str, recording_id: str,
                             new_repair_type: str,
                             repair_number: Optional[int] = None) -> tuple[bool, str]:
        """Change a recording's repair_type in panels.json.

        Args:
            panel_id: The panel that owns this recording.
            recording_id: The recording to reclassify.
            new_repair_type: One of initial, pre_repair, post_repair, check, internal.
            repair_number: Explicit repair number, or None for auto-assign.

        Returns:
            (success, message) tuple.
        """
        try:
            data = self._read_current()
        except Exception as e:
            return False, f"Could not read panels.json: {e}"

        panel = data.get('panels', {}).get(panel_id)
        if panel is None:
            return False, f"Panel '{panel_id}' not found in database"

        # Find the recording
        recordings = panel.get('recordings', [])
        found = False
        for rec in recordings:
            if rec.get('recording_id') == recording_id:
                self._backup()

                rec['repair_type'] = new_repair_type

                # Handle repair number
                if new_repair_type in ('initial', 'baseline', 'check', 'followup', 'internal'):
                    rec['repair_number'] = None
                elif new_repair_type in ('pre_repair', 'post_repair'):
                    if repair_number is not None:
                        rec['repair_number'] = repair_number
                    else:
                        next_num = panel.get('next_repair_number', 1)
                        rec['repair_number'] = next_num
                        # Only increment after a post_repair is assigned
                        if new_repair_type == 'post_repair':
                            panel['next_repair_number'] = next_num + 1

                found = True
                break

        if not found:
            # Recording might be a "discovered" one not in panels.json yet
            # Add it to panels.json
            self._backup()
            meta = self._read_recording_metadata(recording_id)
            if meta is None:
                return False, f"Recording '{recording_id}' not found on disk"

            new_rec = {
                'recording_id': recording_id,
                'recording_path': str(self.recordings_dir / recording_id),
                'timestamp': meta.get('start_time', ''),
                'duration': meta.get('duration_seconds', 0),
                'frame_count': meta.get('frame_count', 0),
                'temp_min': meta.get('temp_range_min', 0),
                'temp_max': meta.get('temp_range_max', 0),
                'temp_avg': (meta.get('temp_range_min', 0) + meta.get('temp_range_max', 0)) / 2,
                'notes': '',
                'repair_type': new_repair_type,
                'repair_number': None,
                'tags': [],
            }

            if new_repair_type in ('pre_repair', 'post_repair'):
                if repair_number is not None:
                    new_rec['repair_number'] = repair_number
                else:
                    next_num = panel.get('next_repair_number', 1)
                    new_rec['repair_number'] = next_num
                    if new_repair_type == 'post_repair':
                        panel['next_repair_number'] = next_num + 1

            recordings.append(new_rec)

        self._write_atomic(data)
        return True, f"Reclassified as '{new_repair_type}'"

    def delete_recordings(self, panel_id: str, recording_ids: list[str],
                          delete_files: bool = False) -> tuple[bool, str]:
        """Remove recordings from panels.json and optionally delete files.

        Args:
            panel_id: The panel to remove recordings from.
            recording_ids: List of recording_ids to remove.
            delete_files: If True, also delete recording folders and report files.

        Returns:
            (success, message) tuple.
        """
        try:
            data = self._read_current()
        except Exception as e:
            return False, f"Could not read panels.json: {e}"

        panel = data.get('panels', {}).get(panel_id)
        if panel is None:
            return False, f"Panel '{panel_id}' not found"

        self._backup()

        ids_to_remove = set(recording_ids)
        original_count = len(panel.get('recordings', []))

        # Remove matching recordings
        panel['recordings'] = [
            rec for rec in panel.get('recordings', [])
            if rec.get('recording_id') not in ids_to_remove
        ]
        removed_count = original_count - len(panel['recordings'])

        # Track hidden recordings so _discover_recordings doesn't re-add them
        if not delete_files:
            hidden = set(panel.get('hidden_recordings', []))
            hidden.update(ids_to_remove)
            panel['hidden_recordings'] = sorted(hidden)

        self._write_atomic(data)

        # Delete files if requested
        files_deleted = 0
        if delete_files:
            # Re-read to check if any other panel still uses these recording_ids
            still_used = set()
            for pid, pdata in data.get('panels', {}).items():
                for rec in pdata.get('recordings', []):
                    rid = rec.get('recording_id')
                    if rid in ids_to_remove:
                        still_used.add(rid)

            for rid in ids_to_remove - still_used:
                # Delete recording folder
                rec_dir = self.recordings_dir / rid
                if rec_dir.exists() and rec_dir.is_dir():
                    shutil.rmtree(rec_dir)
                    files_deleted += 1

                # Delete matching report files
                if self.reports_dir.exists():
                    for report_file in self.reports_dir.iterdir():
                        if report_file.is_file() and rid in report_file.stem:
                            report_file.unlink()

        msg = f"Removed {removed_count} recording(s) from database"
        if delete_files and files_deleted:
            msg += f", deleted {files_deleted} recording folder(s)"
        return True, msg

    def restore_recordings(self, panel_id: str,
                           recording_ids: list[str]) -> tuple[bool, str]:
        """Remove recording IDs from the hidden_recordings list so they get
        rediscovered on the next data reload.

        Returns:
            (success, message) tuple.
        """
        try:
            data = self._read_current()
        except Exception as e:
            return False, f"Could not read panels.json: {e}"

        panel = data.get('panels', {}).get(panel_id)
        if panel is None:
            return False, f"Panel '{panel_id}' not found"

        hidden = set(panel.get('hidden_recordings', []))
        ids_to_restore = set(recording_ids)
        restored = hidden & ids_to_restore

        if not restored:
            return False, "None of the selected recordings were hidden"

        self._backup()
        panel['hidden_recordings'] = sorted(hidden - ids_to_restore)
        self._write_atomic(data)

        return True, f"Restored {len(restored)} recording(s)"

    def generate_json_report(self, panel_id: str, recording,
                             panel_data, temp_min: float = 10.0,
                             temp_max: float = 130.0) -> tuple[bool, str]:
        """Generate a JSON data report for a recording.

        Args:
            panel_id: Panel ID.
            recording: RecordingData object.
            panel_data: PanelData object (for panel metadata).
            temp_min: Temperature scale minimum.
            temp_max: Temperature scale maximum.

        Returns:
            (success, message) tuple.
        """
        from .recording_loader import RecordingLoader

        loader = RecordingLoader(recording.recording_path)
        if not loader.load():
            return False, "Could not load recording files"

        if not loader.find_panel_in_recording(panel_id):
            loader.close()
            return False, "Panel not found in this recording"

        loader.set_colormap(temp_min, temp_max)

        # Compute per-frame stats
        all_stats = loader.get_all_frame_stats(panel_id)
        loader.close()

        if not all_stats or not all_stats.get('mins'):
            return False, "No frame data available"

        frame_statistics = []
        for i in range(len(all_stats['mins'])):
            frame_statistics.append({
                'frame_index': i,
                'timestamp': all_stats['timestamps'][i],
                'temp_min': all_stats['mins'][i],
                'temp_max': all_stats['maxs'][i],
                'temp_avg': all_stats['avgs'][i],
            })

        # Build export matching existing thermal-cam-software format
        overall_min = min(all_stats['mins'])
        overall_max = max(all_stats['maxs'])
        overall_avg = sum(all_stats['avgs']) / len(all_stats['avgs'])

        try:
            dt = datetime.fromisoformat(recording.timestamp)
            timestamp_str = dt.strftime('%Y%m%d_%H%M%S')
        except (ValueError, TypeError):
            timestamp_str = recording.recording_id.replace('recording_', '')

        filename = f"{panel_id}_{recording.repair_type}_{timestamp_str}_data.json"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.reports_dir / filename

        export_data = {
            'version': '1.0',
            'export_date': datetime.now().isoformat(),
            'source': 'ThermaVault Data Manager',
            'panel': {
                'panel_id': panel_data.panel_id,
                'name': panel_data.name,
                'location': panel_data.location or '',
                'manufacturer': panel_data.manufacturer or '',
                'model': panel_data.model or '',
                'serial_number': panel_data.serial_number or '',
                'rated_power': panel_data.rated_power or 0.0,
            },
            'recording': {
                'recording_id': recording.recording_id,
                'timestamp': recording.timestamp,
                'duration': recording.duration,
                'frame_count': recording.frame_count,
                'repair_type': recording.repair_type,
                'repair_number': recording.repair_number,
                'temp_min': recording.temp_min,
                'temp_max': recording.temp_max,
                'temp_avg': recording.temp_avg,
            },
            'summary': {
                'total_frames': len(frame_statistics),
                'duration': recording.duration,
                'overall_temp_min': overall_min,
                'overall_temp_max': overall_max,
                'overall_temp_avg': round(overall_avg, 2),
                'temp_change': round(
                    all_stats['avgs'][-1] - all_stats['avgs'][0], 2
                ) if len(all_stats['avgs']) >= 2 else 0.0,
            },
            'frame_statistics': frame_statistics,
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        return True, str(output_path)

    def rename_panel(self, panel_id: str, new_name: str) -> tuple[bool, str]:
        """Rename a panel's display name in panels.json.

        Only changes the 'name' field. The panel_id (internal key) and all
        recording links remain unchanged.
        """
        try:
            data = self._read_current()
        except Exception as e:
            return False, f"Could not read panels.json: {e}"

        panel = data.get('panels', {}).get(panel_id)
        if panel is None:
            return False, f"Panel '{panel_id}' not found"

        old_name = panel.get('name', panel_id)
        self._backup()
        panel['name'] = new_name
        self._write_atomic(data)

        return True, f"Renamed '{old_name}' → '{new_name}'"

    def import_from_folder(self, source_path: str,
                           copy_files: bool = True) -> tuple[bool, str]:
        """Import new recordings from another ThermalPanel data folder.

        Merges recordings from source panels.json into the local database.
        Only adds recordings that don't already exist (by recording_id).
        Preserves local repair_types, hidden_recordings, and other edits.

        Args:
            source_path: Path to the source ThermalPanel data folder.
            copy_files: If True, copy recording folders and report files.

        Returns:
            (success, message) tuple.
        """
        source_root = Path(source_path)
        source_panels_file = source_root / "panel_data" / "panels.json"
        source_recordings_dir = source_root / "recordings"
        source_reports_dir = source_root / "reports"

        if not source_panels_file.exists():
            return False, "Source folder has no panel_data/panels.json"

        try:
            with open(source_panels_file, 'r', encoding='utf-8') as f:
                source_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return False, f"Could not read source panels.json: {e}"

        try:
            local_data = self._read_current()
        except Exception as e:
            return False, f"Could not read local panels.json: {e}"

        self._backup()

        recordings_added = 0
        recordings_skipped = 0
        panels_added = 0
        files_copied = 0

        for panel_id, source_panel in source_data.get('panels', {}).items():
            local_panel = local_data.get('panels', {}).get(panel_id)
            if local_panel is None:
                # New panel — import it entirely
                local_data.setdefault('panels', {})[panel_id] = source_panel
                local_panel = source_panel
                panels_added += 1

            # Build set of recording IDs already in local DB
            local_rec_ids = set()
            for rec in local_panel.get('recordings') or []:
                rid = rec.get('recording_id')
                if rid:
                    local_rec_ids.add(rid)

            # Also consider hidden recordings as "already known"
            hidden = set(local_panel.get('hidden_recordings') or [])

            for src_rec in source_panel.get('recordings') or []:
                rid = src_rec.get('recording_id')
                if not rid:
                    continue

                if rid in local_rec_ids or rid in hidden:
                    recordings_skipped += 1
                    continue

                # New recording — add it to local DB
                local_panel.setdefault('recordings', []).append(src_rec)
                local_rec_ids.add(rid)
                recordings_added += 1

                # Copy recording folder if requested
                if copy_files and source_recordings_dir.exists():
                    src_rec_dir = source_recordings_dir / rid
                    dst_rec_dir = self.recordings_dir / rid
                    if src_rec_dir.exists() and not dst_rec_dir.exists():
                        shutil.copytree(str(src_rec_dir), str(dst_rec_dir))
                        files_copied += 1

                # Copy matching report files
                if copy_files and source_reports_dir.exists():
                    self.reports_dir.mkdir(parents=True, exist_ok=True)
                    for report_file in source_reports_dir.iterdir():
                        if report_file.is_file() and rid in report_file.stem:
                            dst_report = self.reports_dir / report_file.name
                            if not dst_report.exists():
                                shutil.copy2(str(report_file), str(dst_report))

        # Also scan source recording folders for recordings not in source panels.json
        # (the thermal-cam-software may not have saved them to panels.json yet)
        if copy_files and source_recordings_dir.exists():
            # Build a map of panel_ids we have locally
            local_panels = local_data.get('panels', {})

            for rec_folder in sorted(source_recordings_dir.iterdir()):
                if not rec_folder.is_dir():
                    continue
                rid = rec_folder.name
                meta_path = rec_folder / "metadata.json"
                frames_path = rec_folder / "frames.npz"
                if not meta_path.exists() or not frames_path.exists():
                    continue

                # Already copied?
                dst_rec_dir = self.recordings_dir / rid
                if dst_rec_dir.exists():
                    continue

                # Check if this recording references any local panel
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue

                references_local_panel = False
                for poi in meta.get('pois') or []:
                    pid = poi.get('panel_id')
                    if pid and pid in local_panels:
                        # Check it's not hidden
                        hidden = set(local_panels[pid].get('hidden_recordings') or [])
                        if rid not in hidden:
                            references_local_panel = True
                            break

                if references_local_panel:
                    shutil.copytree(str(rec_folder), str(dst_rec_dir))
                    files_copied += 1

        if panels_added == 0 and recordings_added == 0 and files_copied == 0:
            return True, f"No new data found ({recordings_skipped} recording(s) already in database)"

        if panels_added > 0 or recordings_added > 0:
            self._write_atomic(local_data)

        parts = []
        if panels_added:
            parts.append(f"{panels_added} new panel(s)")
        if recordings_added:
            parts.append(f"{recordings_added} new recording(s)")
        if files_copied:
            parts.append(f"{files_copied} recording folder(s) copied")
        if recordings_skipped:
            parts.append(f"{recordings_skipped} existing skipped")
        msg = "Imported: " + ", ".join(parts)
        return True, msg

    def _read_recording_metadata(self, recording_id: str) -> Optional[dict]:
        """Read metadata.json from a recording folder."""
        meta_path = self.recordings_dir / recording_id / "metadata.json"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
