@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PROMPTFINISHER_v13_EXAKT_exportieren.ps1"
if errorlevel 1 (
  echo.
  echo FEHLER: Der Export konnte nicht abgeschlossen werden.
  echo Das Fenster bleibt offen, damit die Fehlermeldung sichtbar ist.
  pause
)
