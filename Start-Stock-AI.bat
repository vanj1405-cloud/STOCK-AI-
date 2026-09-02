@echo off
cd /d "%~dp0"
start "" cmd /c "python -m streamlit run app.py"
timeout /t 5 /nobreak >nul
start "" http://localhost:8501
