@echo off
cd /d "%~dp0"
echo ====================================================
echo  Starting System Trade Knowledge Base Web UI...
echo  URL: http://localhost:8765
echo  Floorp Panel: Add http://localhost:8765 to sidebar
echo ====================================================

REM Set PYTHONPATH to resolve module errors
set PYTHONPATH=%cd%

REM Try uv run first, fallback to standard python
uv run python tools\kb.py web --port 8765
if %errorlevel% neq 0 (
    echo [Fallback] uv command failed. Trying standard python...
    python tools\kb.py web --port 8765
)

pause
