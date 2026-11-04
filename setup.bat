@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo   MetalAtom 설치 (setup)
echo   app.py 실행에 필요한 패키지를 설치합니다.
echo ==================================================
echo.

rem ---------------------------------------------------------------- 1) Python 찾기
set "PY="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo [오류] Python을 찾을 수 없습니다.
    echo.
    echo   python.org 에서 Python 3.10 이상을 설치한 뒤
    echo   설치 화면에서 "Add Python to PATH" 를 체크하세요.
    echo   설치 후 이 setup.bat 을 다시 실행하세요.
    goto :fail
)

for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%v"
echo 사용할 Python: %PY%  ^(버전 %PYVER%^)
%PY% -c "import sys; print('  python:', sys.executable)"
echo   (web_view.bat 과 같은 Python 입니다.)
echo.

rem ---------------------------------------------------------------- 2) requirements.txt 확인
if not exist "%~dp0requirements.txt" (
    echo [오류] requirements.txt 가 없습니다.
    echo   이 setup.bat 을 requirements.txt 와 같은 폴더에 두세요.
    goto :fail
)

rem ---------------------------------------------------------------- 3) pip 확인
%PY% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo pip 가 없습니다. 설치를 시도합니다...
    %PY% -m ensurepip --upgrade
    if errorlevel 1 goto :pipfail
)
echo.
echo [1/2] 필요한 패키지 설치 중... ^(처음 실행하면 몇 분 걸릴 수 있습니다^)
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo 일반 설치에 실패했습니다. 사용자 폴더에 설치를 다시 시도합니다...
    %PY% -m pip install --user -r "%~dp0requirements.txt"
    if errorlevel 1 goto :pipfail
)

rem ---------------------------------------------------------------- 4) 설치 확인
echo.
echo [2/2] 설치 확인 중...
%PY% -c "import streamlit, numpy, matplotlib; print('  streamlit', streamlit.__version__); print('  numpy    ', numpy.__version__); print('  matplotlib', matplotlib.__version__)"
if errorlevel 1 goto :verifyfail

echo.
echo ==================================================
echo   설치 완료!
echo.
echo   이제 web_view.bat 을 더블클릭하면 앱이 열립니다.
echo   ^(브라우저 주소: http://localhost:8501^)
echo ==================================================
echo.
pause
exit /b 0

:pipfail
echo.
echo ==================================================
echo   [실패] 패키지 설치에 실패했습니다.
echo.
echo   확인해 볼 것:
echo     - 인터넷 연결 (사내망이면 프록시 설정)
echo     - 아래 명령을 직접 실행해 오류 메시지 확인:
echo         %PY% -m pip install -r requirements.txt
echo     - pip 자체가 깨졌다면:
echo         %PY% -m ensurepip --upgrade
echo ==================================================
echo.
pause
exit /b 1

:verifyfail
echo.
echo ==================================================
echo   [실패] 설치는 되었지만 import 확인에 실패했습니다.
echo   위의 오류 메시지를 확인하세요.
echo   Python 버전이 너무 새로우면 3.10~3.13 사용을 권장합니다.
echo ==================================================
echo.
pause
exit /b 1

:fail
echo.
pause
exit /b 1
