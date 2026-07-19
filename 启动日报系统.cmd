@echo off
setlocal
cd /d "%~dp0"
set "SCRIPT=%~dp0scripts\start_all.ps1"
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%SCRIPT%" (
  echo [start_all] Missing scripts\start_all.ps1
  echo [start_all] Press any key to close this window.
  pause >nul
  exit /b 1
)

if not exist "%POWERSHELL_EXE%" (
  echo [start_all] powershell.exe was not found.
  echo [start_all] Press any key to close this window.
  pause >nul
  exit /b 1
)

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" echo [start_all] Startup script exited with code %EXITCODE%.
echo [start_all] Press any key to close this window.
pause >nul
exit /b %EXITCODE%