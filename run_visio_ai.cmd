@echo off
setlocal
title VISIO-NETRA local server
set "PYTHON_EXE=C:\Users\zaina\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if "%VISIO_AI_PORT%"=="" (
  for /f %%P in ('powershell -NoProfile -Command "if (Test-NetConnection 127.0.0.1 -Port 8765 -InformationLevel Quiet) { 8766 } else { 8765 }"') do set "VISIO_AI_PORT=%%P"
)

echo Starting VISIO-NETRA at http://127.0.0.1:%VISIO_AI_PORT%
start "" cmd /c "timeout /t 2 >nul & start "" http://127.0.0.1:%VISIO_AI_PORT%"
"%PYTHON_EXE%" "%~dp0visio_ai_server.py"
pause
