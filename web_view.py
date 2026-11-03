# -*- coding: utf-8 -*-
"""MetalAtom 웹 실행기.

결과 파일만 보는 것이 아니라, 시뮬레이션 화면(웹 UI) 자체를 띄웁니다.
실행 방법:
  - Windows: web_view.bat 더블클릭
  - 어디서나: python web_view.py
그러면 이 폴더의 app.py를 Streamlit 서버로 실행하고 브라우저가
자동으로 열립니다 (http://localhost:8501).
종료하려면 이 창에서 Ctrl+C를 누르세요.

이 파일은 표준 라이브러리만 사용합니다. Streamlit이 없으면
설치 안내를 출력하고 종료합니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")
URL = "http://localhost:8501"


def streamlit_available():
    """현재 Python에 Streamlit이 설치되어 있는지 확인."""
    try:
        r = subprocess.run([sys.executable, "-m", "streamlit", "--version"],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    if "streamlit" in os.path.basename(sys.argv[0]).lower():
        print("web_view.py는 'streamlit run web_view.py'로 실행하지 않습니다.")
        print("대신 python web_view.py 로 실행하세요 (앱은 app.py입니다).")
        return 2
    if not os.path.exists(APP):
        print("app.py를 찾을 수 없습니다:", APP)
        print("web_view.py와 app.py가 같은 폴더에 있어야 합니다.")
        return 1
    if not streamlit_available():
        print("Streamlit이 설치되어 있지 않습니다.")
        print("먼저 설치하세요: pip install -r requirements.txt")
        return 1
    print("MetalAtom을 웹으로 엽니다...")
    print("브라우저 주소:", URL)
    print("브라우저가 자동으로 열리지 않으면 위 주소를 직접 입력하세요.")
    print("종료하려면 이 창에서 Ctrl+C를 누르세요.")
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", APP],
                            cwd=HERE)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
