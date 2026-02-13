"""Application settings persistence via QSettings."""

from PyQt6.QtCore import QSettings, QByteArray


class AppSettings:
    """Persists user preferences."""

    def __init__(self):
        self._settings = QSettings("ThermaVault", "ThermaVault")

    @property
    def last_data_folder(self) -> str:
        return self._settings.value("data/last_folder", "", type=str)

    @last_data_folder.setter
    def last_data_folder(self, path: str):
        self._settings.setValue("data/last_folder", path)

    @property
    def recent_folders(self) -> list:
        return self._settings.value("data/recent_folders", [], type=list)

    @recent_folders.setter
    def recent_folders(self, folders: list):
        self._settings.setValue("data/recent_folders", folders[:10])

    def add_recent_folder(self, path: str):
        recent = self.recent_folders
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        self.recent_folders = recent[:10]

    @property
    def window_geometry(self) -> QByteArray:
        return self._settings.value("ui/geometry", QByteArray())

    @window_geometry.setter
    def window_geometry(self, geom: QByteArray):
        self._settings.setValue("ui/geometry", geom)

    @property
    def splitter_state(self) -> QByteArray:
        return self._settings.value("ui/splitter", QByteArray())

    @splitter_state.setter
    def splitter_state(self, state: QByteArray):
        self._settings.setValue("ui/splitter", state)

    @property
    def temp_range_min(self) -> float:
        return self._settings.value("playback/temp_min", 10.0, type=float)

    @temp_range_min.setter
    def temp_range_min(self, val: float):
        self._settings.setValue("playback/temp_min", val)

    @property
    def temp_range_max(self) -> float:
        return self._settings.value("playback/temp_max", 130.0, type=float)

    @temp_range_max.setter
    def temp_range_max(self, val: float):
        self._settings.setValue("playback/temp_max", val)

    @property
    def verified_recordings(self) -> list:
        return self._settings.value("data/verified_recordings", [], type=list)

    def add_verified_recording(self, recording_id: str):
        verified = self.verified_recordings
        if recording_id not in verified:
            verified.append(recording_id)
            self._settings.setValue("data/verified_recordings", verified)

    def is_recording_verified(self, recording_id: str) -> bool:
        return recording_id in self.verified_recordings
