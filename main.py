"""ThermaVault - Thermal Panel Data Viewer."""

import sys
from PyQt6.QtWidgets import QApplication
from src.app import MainWindow
from src.theme import ThemeManager


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ThermaVault")
    app.setOrganizationName("ThermaVault")
    app.setStyle("Fusion")

    ThemeManager.instance().load_preference()

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
