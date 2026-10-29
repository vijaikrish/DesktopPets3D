@echo off
rem DesktopPets3D - one-time setup on Windows: a private Python environment (.venv) with PySide6 + numpy.
rem Needs Python 3.10 or newer from https://www.python.org (tick "Add python.exe to PATH" or use the py launcher).
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Could not create .venv - is Python 3.10+ installed?
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Done. Start the bird with run.bat
pause
endlocal
