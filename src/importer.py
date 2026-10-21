"""Locate the ThermalPanel data inside an import source (folder or Export Package zip)."""

import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional, Tuple

from .exporter import DATA_FOLDER

PANELS_JSON = "panel_data/panels.json"

# Parts of a data folder that are never imported: the capture app and the
# source PC's own panels.json backups.
_SKIP_TOP = {'thermalpanel.exe', '_internal'}
_SKIP_PREFIXES = ('panel_data/backups/',)


def find_data_folder(folder: str) -> Optional[Path]:
    """Data folder for a picked folder: the folder itself or its ThermalPanel subfolder."""
    root = Path(folder)
    for candidate in (root, root / DATA_FOLDER):
        if (candidate / PANELS_JSON).is_file():
            return candidate
    return None


def _zip_data_prefix(names) -> Optional[str]:
    """Path prefix of the data folder inside the zip ('' for a zipped data folder)."""
    prefixes = [n[:-len(PANELS_JSON)] for n in names
                if n == PANELS_JSON or n.endswith('/' + PANELS_JSON)]
    if not prefixes:
        return None
    # Prefer the shallowest match (the package's ThermalPanel/ folder)
    return min(prefixes, key=lambda p: p.count('/'))


def _always_needed(rel: str) -> bool:
    """Files that are read even when a local copy exists (they get merged)."""
    return rel == PANELS_JSON or (rel.startswith('panel_data/annotations/')
                                  and rel.endswith('/annotations.json'))


def is_skipped(rel: str) -> bool:
    """True for paths (relative to the data folder) that are never imported."""
    top = rel.split('/', 1)[0].lower()
    return (top in _SKIP_TOP or rel.startswith(_SKIP_PREFIXES)
            or rel.endswith('.tmp') or PurePosixPath(rel).name.lower() == 'nul')


def extract_package(zip_path: str, local_root: str,
                    progress: Optional[Callable[[int, int, str], None]] = None,
                    is_cancelled: Optional[Callable[[], bool]] = None
                    ) -> Tuple[Optional[Path], Optional[Path], str]:
    """Extract the data folder of an Export Package to a temp dir.

    Only files missing from local_root are extracted (plus panels.json and
    annotations.json, which are merged), so re-importing a package is quick.

    Returns:
        (data_folder, temp_dir_to_remove, error). data_folder is None on error
        or cancel; the temp dir is already removed in that case.
    """
    local = Path(local_root)
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        return None, None, f"Could not open zip: {e}"

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        prefix = _zip_data_prefix([i.filename for i in infos])
        if prefix is None:
            return None, None, "The zip has no ThermalPanel data (panel_data/panels.json)"

        wanted = []
        for info in infos:
            if not info.filename.startswith(prefix):
                continue
            rel = info.filename[len(prefix):]
            parts = PurePosixPath(rel).parts
            if not parts or '..' in parts or PurePosixPath(rel).is_absolute() or ':' in rel:
                continue  # unsafe path
            if is_skipped(rel):
                continue
            if _always_needed(rel) or not (local / rel).exists():
                wanted.append((info, rel))

        total = sum(i.file_size for i, _ in wanted)
        done = 0
        tmp = Path(tempfile.mkdtemp(prefix="thermavault_import_"))
        data_dir = tmp / DATA_FOLDER
        try:
            for info, rel in wanted:
                if is_cancelled and is_cancelled():
                    raise InterruptedError
                if progress:
                    progress(done, total, rel)
                dest = data_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                done += info.file_size
        except InterruptedError:
            shutil.rmtree(tmp, ignore_errors=True)
            return None, None, "Import cancelled"
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            return None, None, f"Could not extract zip: {e}"

    if progress:
        progress(total, total, "")
    return data_dir, tmp, ""
