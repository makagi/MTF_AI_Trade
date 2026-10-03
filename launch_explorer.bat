@echo off
cd /d "%~dp0"
echo ====================================================
echo  Starting Interactive Dataset Explorer...
echo  This dashboard allows you to dynamically visualize
echo  the exhaustive feature dataset (SMAs, BBs, AFS).
echo ====================================================

set PYTHONPATH=%cd%

uv run streamlit run tools\dataset_explorer.py
if %errorlevel% neq 0 (
    echo [Fallback] uv command failed. Trying standard python...
    streamlit run tools\dataset_explorer.py
)

pause
