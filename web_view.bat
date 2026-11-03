@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python이 설치되어 있지 않습니다. python.org에서 Python을 설치하세요.
    pause
    exit /b 1
)
python web_view.py
if errorlevel 1 (
    echo.
    echo 실행에 실패했습니다. Streamlit 설치 여부를 확인하세요:
    echo pip install -r requirements.txt
    pause
)
