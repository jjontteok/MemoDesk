@echo off
rem MemoDesk 켜기 — 더블클릭. 이미 켜져 있으면 브라우저만 연다.
rem 이 창을 닫으면 MemoDesk 가 꺼지고 돌던 작업이 끊긴다(다음에 켤 때 되돌리고 그 프로젝트를 멈춤으로 둔다). 최소화는 괜찮다.
chcp 65001 >nul
title MemoDesk - 이 창을 닫으면 꺼집니다
cd /d "%~dp0"

rem 프록시를 거치지 않고 묻는다 — 회사 PC 는 127.0.0.1 요청도 프록시로 보내 '안 켜짐'으로 잘못 읽힐 수 있다
powershell -NoProfile -Command "try { $r = [System.Net.WebRequest]::Create('http://127.0.0.1:8791/api/state'); $r.Proxy = $null; $r.Timeout = 2000; $r.GetResponse().Close(); exit 10 } catch { exit 0 }" >nul 2>&1
if errorlevel 10 (
  start "" http://127.0.0.1:8791
  exit /b 0
)

echo MemoDesk 를 켭니다. 이 창은 닫지 말고 최소화해 두세요. 끌 때는 Ctrl+C.
start "" cmd /c ""%SystemRoot%\System32\timeout.exe" /t 2 >nul & start http://127.0.0.1:8791"
python -B -m memodesk %*

echo.
echo MemoDesk 가 꺼졌습니다. 위에 오류가 있으면 확인하세요.
pause
