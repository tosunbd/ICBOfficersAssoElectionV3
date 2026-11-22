@echo off
rem Double-click to stop the ICB Election System (closes the API and UI).
title ICB Election System - Stop
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\stop-local.ps1"
echo.
pause
