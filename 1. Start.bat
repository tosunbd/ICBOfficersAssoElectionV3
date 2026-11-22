@echo off
rem Double-click to start the ICB Election System (API + UI in two windows).
rem Serves the production UI (rebuilt only when it changed); after install.bat
rem it is also reachable from the LAN as http://<this-pc-ip>/election/...
title ICB Election System - Start
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start-local.ps1" -Production
echo.
pause
