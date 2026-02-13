"""
Theme management for ThermaVault.

Simplified from ThermalPanel's theme system - keeps only QSS-relevant colors.
"""

from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal, QSettings


@dataclass(frozen=True)
class ThemeColors:
    """Color palette for one theme."""

    # Window / app-level backgrounds
    window_bg: str
    widget_bg: str
    surface_bg: str

    # Borders
    border: str
    border_hover: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_disabled: str

    # Buttons
    button_bg: str
    button_hover: str
    button_pressed: str

    # Scrollbar
    scrollbar_bg: str
    scrollbar_handle: str
    scrollbar_handle_hover: str

    # Accent colors
    accent_green: str
    accent_blue: str
    accent_yellow: str
    accent_red: str
    accent_orange: str


DARK_THEME = ThemeColors(
    window_bg="#0c0e14",
    widget_bg="#1a1e2e",
    surface_bg="#1a1a2e",
    border="#2a3050",
    border_hover="#4e5580",
    text_primary="#e8eaf0",
    text_secondary="#8b92ab",
    text_muted="#888888",
    text_disabled="#666666",
    button_bg="#1a1e2e",
    button_hover="#232840",
    button_pressed="#4e8fff",
    scrollbar_bg="#1a1e2e",
    scrollbar_handle="#3a4060",
    scrollbar_handle_hover="#4e5580",
    accent_green="#47d4a0",
    accent_blue="#4e8fff",
    accent_yellow="#f5c842",
    accent_red="#ff3366",
    accent_orange="#ff6b4a",
)

LIGHT_THEME = ThemeColors(
    window_bg="#f0f2f5",
    widget_bg="#ffffff",
    surface_bg="#f5f5f8",
    border="#c0c4cc",
    border_hover="#8090b0",
    text_primary="#1a1e2e",
    text_secondary="#555570",
    text_muted="#777790",
    text_disabled="#aaaaaa",
    button_bg="#e8eaf0",
    button_hover="#d0d4e0",
    button_pressed="#4e8fff",
    scrollbar_bg="#e0e2e8",
    scrollbar_handle="#b0b4c0",
    scrollbar_handle_hover="#8090a0",
    accent_green="#2ba87a",
    accent_blue="#2a6edb",
    accent_yellow="#c49a10",
    accent_red="#d42850",
    accent_orange="#d44a2a",
)


class ThemeManager(QObject):
    """Singleton that manages current theme and notifies on change."""

    theme_changed = pyqtSignal()

    _instance = None

    @classmethod
    def instance(cls) -> 'ThemeManager':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._current = DARK_THEME
        self._is_dark = True

    @property
    def colors(self) -> ThemeColors:
        return self._current

    @property
    def is_dark(self) -> bool:
        return self._is_dark

    def set_dark(self):
        self._current = DARK_THEME
        self._is_dark = True
        self._save_preference()
        self.theme_changed.emit()

    def set_light(self):
        self._current = LIGHT_THEME
        self._is_dark = False
        self._save_preference()
        self.theme_changed.emit()

    def toggle(self):
        if self._is_dark:
            self.set_light()
        else:
            self.set_dark()

    def load_preference(self):
        settings = QSettings("ThermaVault", "ThermaVault")
        is_dark = settings.value("theme/dark_mode", True, type=bool)
        self._is_dark = is_dark
        self._current = DARK_THEME if is_dark else LIGHT_THEME

    def _save_preference(self):
        settings = QSettings("ThermaVault", "ThermaVault")
        settings.setValue("theme/dark_mode", self._is_dark)


def current_theme() -> ThemeColors:
    """Get current theme colors."""
    return ThemeManager.instance().colors
