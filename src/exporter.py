"""Export a portable package (app + full data folder) as a single zip file."""

import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Folder names inside the package. On startup ThermaVault looks for
# ../ThermalPanel next to its own folder, so a package works right after unzipping.
APP_FOLDER = "ThermaVault"
DATA_FOLDER = "ThermalPanel"

# Already-compressed formats are stored as-is (deflating them gains <2%).
_STORE_EXTENSIONS = {'.npz', '.zip', '.png', '.jpg', '.jpeg', '.pdf', '.mp4', '.avi'}

# Parts of a ThermalPanel folder that are the capture app, not data.
_CAPTURE_APP_ITEMS = {'thermalpanel.exe', '_internal'}


def app_folder() -> Optional[Path]:
    """Folder of the running portable build, or None when running from source."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return None


def bundled_data_folder() -> Optional[str]:
    """ThermalPanel data folder that sits next to the app folder (as in a package)."""
    app_dir = app_folder()
    if app_dir is None:
        return None
    candidate = app_dir.parent / DATA_FOLDER
    if (candidate / "panel_data" / "panels.json").exists():
        return str(candidate)
    return None


def collect_files(data_root: str, include_app: bool, include_capture_app: bool,
                  exclude: Optional[Path] = None) -> List[Tuple[Path, str]]:
    """List (source file, name in zip) pairs for the package."""
    files: List[Tuple[Path, str]] = []

    def add_tree(src_root: Path, arc_root: str, skip_top: set = frozenset()):
        for dirpath, dirnames, filenames in os.walk(src_root):
            current = Path(dirpath)
            at_top = current == src_root
            dirnames[:] = sorted(
                d for d in dirnames
                if not d.startswith('.') and not (at_top and d.lower() in skip_top)
            )
            for name in sorted(filenames):
                if at_top and name.lower() in skip_top:
                    continue
                if name.endswith('.tmp') or name.lower() == 'nul':
                    continue
                path = current / name
                if exclude is not None and path.resolve() == exclude:
                    continue
                arcname = f"{arc_root}/{path.relative_to(src_root).as_posix()}"
                files.append((path, arcname))

    if include_app:
        app_dir = app_folder()
        if app_dir is not None:
            add_tree(app_dir, APP_FOLDER)

    skip = set() if include_capture_app else _CAPTURE_APP_ITEMS
    add_tree(Path(data_root), DATA_FOLDER, skip)
    return files


def _readme(data_root: str, files: List[Tuple[Path, str]], include_app: bool) -> str:
    recordings = {a.split('/')[2] for _, a in files
                  if a.startswith(f"{DATA_FOLDER}/recordings/") and a.count('/') >= 3}
    reports = [a for _, a in files if a.startswith(f"{DATA_FOLDER}/reports/")]
    lines = [
        "THERMAVAULT EXPORT PACKAGE",
        "==========================",
        f"Created:      {datetime.now():%Y-%m-%d %H:%M}",
        f"Exported from: {data_root}",
        "",
        "Contents",
    ]
    if include_app:
        lines.append(f"  {APP_FOLDER}\\     - ThermaVault viewer (no install needed)")
    lines += [
        f"  {DATA_FOLDER}\\    - all data: panels, annotations, backups,",
        f"                    {len(recordings)} recordings, {len(reports)} report files",
        "",
        "On the new PC",
    ]
    if include_app:
        lines += [
            "  1. Unzip anywhere (keep both folders side by side).",
            f"  2. Run {APP_FOLDER}\\ThermaVault.exe.",
            f"     It opens the {DATA_FOLDER} folder next to it automatically.",
        ]
    else:
        lines += [
            "  1. Unzip anywhere.",
            f"  2. In ThermaVault use File > Open Folder and pick {DATA_FOLDER}.",
        ]
    lines += [
        "",
        "Recordings are found inside the data folder itself, so the package",
        "can be placed on any drive or path.",
    ]
    return "\n".join(lines) + "\n"


def export_package(data_root: str, dest_zip: str, include_app: bool = True,
                   include_capture_app: bool = True,
                   progress: Optional[Callable[[int, int, str], None]] = None,
                   is_cancelled: Optional[Callable[[], bool]] = None) -> Tuple[bool, str]:
    """Write the package zip.

    Args:
        data_root: ThermalPanel data folder to export.
        dest_zip: Output .zip path.
        include_app: Include the running ThermaVault build (portable build only).
        include_capture_app: Include ThermalPanel.exe + _internal from the data folder.
        progress: Called as progress(bytes_done, bytes_total, current_file).
        is_cancelled: Polled between files; returning True aborts the export.

    Returns:
        (success, message) tuple.
    """
    dest = Path(dest_zip).resolve()
    files = collect_files(data_root, include_app, include_capture_app, exclude=dest)
    total = sum(p.stat().st_size for p, _ in files)
    tmp = dest.with_name(dest.name + ".part")
    done = 0

    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            zf.writestr("README.txt", _readme(data_root, files, include_app))
            for path, arcname in files:
                if is_cancelled and is_cancelled():
                    raise InterruptedError
                if progress:
                    progress(done, total, arcname)
                compress = (zipfile.ZIP_STORED if path.suffix.lower() in _STORE_EXTENSIONS
                            else zipfile.ZIP_DEFLATED)
                zf.write(path, arcname, compress_type=compress)
                done += path.stat().st_size
        os.replace(tmp, dest)
    except InterruptedError:
        tmp.unlink(missing_ok=True)
        return False, "Export cancelled"
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return False, f"Export failed: {e}"

    if progress:
        progress(total, total, "")
    size_mb = dest.stat().st_size / 1e6
    return True, f"Exported {len(files)} files ({size_mb:,.0f} MB) to:\n{dest}"
