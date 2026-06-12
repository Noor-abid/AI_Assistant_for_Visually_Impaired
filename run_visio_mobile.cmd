@echo off
setlocal
title VISIO-NETRA mobile server
set "PYTHON_EXE=C:\Users\zaina\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "VISIO_AI_HOST=0.0.0.0"
if "%VISIO_AI_PORT%"=="" (
  for /f %%P in ('powershell -NoProfile -Command "if (Test-NetConnection 127.0.0.1 -Port 8765 -InformationLevel Quiet) { 8766 } else { 8765 }"') do set "VISIO_AI_PORT=%%P"
)

echo Starting VISIO-NETRA mobile server.
echo Open http://YOUR-COMPUTER-IP:%VISIO_AI_PORT% on a phone connected to the same Wi-Fi.
echo For camera access on a real phone, use HTTPS or install/run it from a secure host.
"%PYTHON_EXE%" "%~dp0visio_ai_server.py"
pause
