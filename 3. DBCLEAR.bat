@echo off
rem Double-click just before the election starts: saves a backup of the current
rem database to data\Archive, then empties it (admin logins are kept).
rem The file cleared is data\icbOfficerAssoDB<year>.db for the year set in
rem Admin -> Settings -> Database (or ELECTION_YEAR in .env).
title ICB Election System - Clear database
cd /d "%~dp0"
chcp 65001 >nul
if not exist "icbOfficerAssoAPI\.venv\Scripts\python.exe" (
  echo The API is not set up yet. Run scripts\setup-local.ps1 first.
  echo.
  pause
  exit /b 1
)
"icbOfficerAssoAPI\.venv\Scripts\python.exe" "icbOfficerAssoAPI\scripts\clear_db.py"
echo.
pause
