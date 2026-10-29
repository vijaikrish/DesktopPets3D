@echo off
rem DesktopPets3D - start from source on Windows, without a console window.
rem Uses .venv (made by setup_windows.bat) if it exists, otherwise the Python launcher (pyw -3).
rem run_debug.bat does the same with a console, to see errors.
setlocal
set PYTHONPATH=
set PYTHONHOME=
set VIRTUAL_ENV=
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "DesktopPets3D" ".venv\Scripts\pythonw.exe" -m app.desktop %*
  goto :eof
)
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "DesktopPets3D" pyw -3 -m app.desktop %*
) else (
  start "DesktopPets3D" pythonw -m app.desktop %*
)
endlocal
