@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_all.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo [start_all] 启动脚本已退出，退出码 %EXITCODE%。
echo [start_all] 按任意键关闭窗口。
pause >nul
exit /b %EXITCODE%