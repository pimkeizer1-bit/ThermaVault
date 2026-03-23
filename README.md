# ThermaVault

A desktop application for browsing, analyzing, and managing thermal imaging recordings from heating panels. Built with PyQt6, it provides thermal video playback, temperature visualization, repair tracking, and panel data management.

ThermaVault is a **viewer and data management tool only** — it does not interface with thermal cameras. Recordings must be captured separately (e.g. by the ThermalPanel acquisition system) and provided as `.npz`/`.json` files on disk.

## Features

- **Thermal playback** — view recordings with configurable colormaps (ironbow, rainbow, grayscale, hot, cool/warm, plasma) and adjustable temperature ranges
- **Panel management** — track panel metadata (location, manufacturer, serial number, power rating), rename, merge, and tag panels
- **Repair tracking** — link before/after recordings to repair events with temperature improvement metrics
- **Recording triage** — classify recordings as baseline, pre-repair, post-repair, or hidden; bulk operations via Data Manager tab
- **Field notes** — attach photos (file or webcam) and comments to recordings
- **Reports & QR codes** — generate JSON reports and QR codes for panel identification; optional DYMO label printing (Windows)
- **Import & merge** — import recordings and panel data from other data folders without overwriting existing data
- **Data safety** — all modifications create timestamped backups; atomic writes prevent corruption

## Prerequisites

- Python 3.8+
- On Windows: optional [pywin32](https://pypi.org/project/pywin32/) for DYMO printer support

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

On Windows you can also use `run.bat`.

On first launch, select your data folder containing the `panel_data/` and `recordings/` directories.

### Portable build (Windows)

Run `build_portable.bat` to create a standalone executable via PyInstaller in `dist/ThermaVault/`. No Python installation required on the target machine.

## Data folder structure

```
data_root/
  panel_data/
    panels.json            Main panel database
    backups/               Auto-generated backups
    annotations/           Field notes (photos + comments)
  recordings/
    recording_XXXX/
      metadata.json
      frames.npz           Thermal frame data (NumPy compressed)
  reports/                 Generated reports
  QR codes/                Generated QR code images
```

## Architecture

```
main.py                         Entry point
├── src/
│   ├── app.py                  Main window, menu bar, theme switching
│   ├── models.py               Data models (PanelData, RecordingData, RepairEvent)
│   ├── data_loader.py          Read-only data loading, search, filtering
│   ├── data_writer.py          Safe writes with backup, classification, import
│   ├── recording_loader.py     Thermal frame loading, perspective correction, stats
│   ├── colormap.py             Temperature-to-color mapping (6 schemes, LUT-based)
│   ├── annotations.py          Field note management (photos + comments)
│   ├── settings.py             Persistent app settings via QSettings
│   ├── theme.py                Dark/light theme with full color palette
│   ├── utils/
│   │   └── file_matching.py    Report/QR filename parsing
│   └── widgets/
│       ├── panel_list.py       Searchable panel sidebar
│       ├── panel_detail.py     Tabbed detail view (recordings, playback, reports, etc.)
│       ├── recording_viewer.py Thermal frame display with playback controls
│       └── recordings_browser.py  Global recording view with triage mode
```

## License

All rights reserved.
