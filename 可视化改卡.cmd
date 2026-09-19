@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: drag a card folder onto this file to open the visual card editor.
  pause
  exit /b 1
)
echo Starting visual editor for: %~1
poetry run python scripts/card_editor.py "%~1"
pause
