@echo off
rem Double-click once on every PC that will run the election system (needs the
rem internet).  Installs / finds Python and Node.js, builds a fresh Python
rem virtual environment for THIS PC, installs all packages, builds the UI and
rem publishes it through IIS:
rem     http://<this-pc-ip>/election/admin      http://<this-pc-ip>/election/dashboard
rem Safe to run again (finished steps are skipped).  Then use "1. Start.bat".
setlocal

rem ------------------------------------------------- settings you may change
rem Python version the API needs; an installed 64-bit copy of it is used if
rem one is found, otherwise it is installed into PYTHON_INSTALL_DIR (other
rem Python versions on the PC are not touched).
set "PYTHON_VERSION=3.14"
set "PYTHON_INSTALL_DIR=C:\Python\Python314"
rem Oldest Node.js accepted; older or missing -> a private copy in tools\node.
set "NODE_MIN_VERSION=20.9.0"
rem IIS site and URL prefix the system is published under (port 80).
set "IIS_SITE=Default Web Site"
set "IIS_APP_PATH=/election"
rem yes = do not set up IIS / firewall (then use http://<pc>:3000 directly).
set "SKIP_IIS=no"
rem yes = always delete and rebuild icbOfficerAssoAPI\.venv.  A .venv copied
rem from another PC is rebuilt automatically anyway.
set "RECREATE_VENV=no"
rem ---------------------------------------------------------------------------

title ICB Election System - Install
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo Asking for administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "EXTRA="
if /i "%SKIP_IIS%"=="yes" set "EXTRA=%EXTRA% -SkipIis"
if /i "%RECREATE_VENV%"=="yes" set "EXTRA=%EXTRA% -RecreateVenv"

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\install.ps1" -PythonVersion "%PYTHON_VERSION%" -PythonInstallDir "%PYTHON_INSTALL_DIR%" -NodeMinVersion "%NODE_MIN_VERSION%" -IisSite "%IIS_SITE%" -IisAppPath "%IIS_APP_PATH%" %EXTRA%
if errorlevel 1 (
  echo.
  echo INSTALLATION FAILED - see the message above, fix it and run "0. install.bat" again.
)
echo.
pause
