@echo off
rem DesktopPets3D - start from source with a console window (shows errors). Close the console to quit.
setlocal
set PYTHONPATH=
set PYTHONHOME=
set VIRTUAL_ENV=
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m app.desktop %*
) else (
  goto :launcher
)
goto :done
:launcher
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m app.desktop %*
) else (
  python -m app.desktop %*
)
:done
echo.
echo Log file: %APPDATA%\DesktopPets3D\logs\desktoppets3d.log
pause
endlocal
