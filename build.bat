@echo off
echo Building alyPyAcquisition...
echo.

pyinstaller --onedir --windowed --name "alyPyAcquisition" --add-data "config.ini;." main.py

echo.
if %ERRORLEVEL% EQU 0 (
    echo Build successful! Output is in dist\alyPyAcquisition\
    echo Run dist\alyPyAcquisition\alyPyAcquisition.exe to launch.
) else (
    echo Build FAILED with error code %ERRORLEVEL%
)
pause
