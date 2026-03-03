@echo off
echo ========================================
echo Building Portable ThermaVault
echo ========================================
echo.

REM Install PyInstaller if not present
pip install pyinstaller

echo.
echo Cleaning previous build...
echo.

cd /d "%~dp0"

REM Clean BEFORE building to avoid stale cache
rmdir /s /q "build" 2>nul
rmdir /s /q "dist\ThermaVault" 2>nul
del "ThermaVault.spec" 2>nul

echo Building executable...
echo.

pyinstaller --noconfirm --onedir --windowed ^
    --name "ThermaVault" ^
    --paths "src" ^
    --hidden-import "src" ^
    --hidden-import "src.app" ^
    --hidden-import "src.data_loader" ^
    --hidden-import "src.data_writer" ^
    --hidden-import "src.recording_loader" ^
    --hidden-import "src.colormap" ^
    --hidden-import "src.settings" ^
    --hidden-import "src.theme" ^
    --hidden-import "src.models" ^
    --hidden-import "src.qr_generator" ^
    --hidden-import "src.annotations" ^
    --hidden-import "src.utils" ^
    --hidden-import "src.utils.file_matching" ^
    --hidden-import "src.widgets" ^
    --hidden-import "src.widgets.panel_list" ^
    --hidden-import "src.widgets.panel_detail" ^
    --hidden-import "src.widgets.recording_viewer" ^
    --hidden-import "src.widgets.recording_table" ^
    --hidden-import "src.widgets.report_list" ^
    --hidden-import "src.widgets.repair_timeline" ^
    --hidden-import "src.widgets.qr_display" ^
    --hidden-import "src.widgets.field_notes" ^
    --hidden-import "src.widgets.webcam_dialog" ^
    --hidden-import "src.widgets.data_manager" ^
    --hidden-import "qrcode" ^
    --hidden-import "PIL" ^
    --hidden-import "PIL.Image" ^
    --collect-submodules "src" ^
    --exclude-module "tkinter" ^
    --exclude-module "_tkinter" ^
    --exclude-module "matplotlib" ^
    main.py

echo.
echo Cleaning up build artifacts...
rmdir /s /q "build" 2>nul
del "ThermaVault.spec" 2>nul

echo.
echo ========================================
echo Build complete!
echo.
echo Portable version is in: dist\ThermaVault\
echo.
echo To deploy:
echo   1. Copy the entire "dist\ThermaVault" folder to USB
echo   2. Run ThermaVault.exe on any Windows PC
echo   3. Point it at a ThermalPanel data folder
echo ========================================
pause
