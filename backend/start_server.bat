@echo off
rem 찐맛집 백엔드 서버 시작 (실사용용)
rem - 0.0.0.0:8000 으로 열어 폰(Tailscale/LAN)에서 접속 허용
rem - .env 의 GOOGLE_PLACES_API_KEY 자동 로딩 (키는 파일에만 있음)
rem - ZAI_API_KEY 는 Windows 사용자 환경변수에서 자동으로 상속됨
cd /d %~dp0

if exist .env (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="GOOGLE_PLACES_API_KEY" set "GOOGLE_PLACES_API_KEY=%%B"
  )
)

set ZAI_MODEL=glm-4.5-flash
set ZAI_SKIP_MODEL_CHECK=1

echo ============================================
echo  찐맛집 백엔드 시작: http://0.0.0.0:8000
echo  폰 앱에 넣을 주소:
echo   Tailscale : http://100.79.12.113:8000
echo   같은 와이파이 : http://192.168.219.111:8000
echo ============================================

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
