@echo off
rem Double-click to open the real2sim app in the browser. Extra arguments are passed on,
rem e.g.  real2sim.bat --no-browser --port 8766
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv - see README.md, section "Cai dat".
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m real2sim app %*
