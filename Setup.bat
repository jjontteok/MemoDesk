@echo off
rem MemoDesk 처음 설치 — 더블클릭. 파이썬이 없으면 winget 으로 설치한 뒤 MemoDesk 를 켠다.
rem Claude Code CLI · 로그인 · Git 은 켜진 화면의 "시작하기 전에" 점검표에서 버튼으로 설치한다(파이썬이 있어야 화면이 켜진다).
chcp 65001 >nul
title MemoDesk 설치
cd /d "%~dp0"

echo.
echo [1/2] 파이썬 확인
call :findpy
if not defined PY (
  where winget >nul 2>&1
  if errorlevel 1 (
    echo     winget 이 없어 자동으로 설치할 수 없습니다.
    echo     https://www.python.org/downloads/ 에서 파이썬 3.12 를 설치한 뒤 이 파일을 다시 실행하세요.
    echo     설치할 때 "Add python.exe to PATH" 에 체크하세요.
    pause
    exit /b 1
  )
  echo     파이썬 3.12 를 설치합니다 ^(winget, 이 사용자에게만 — 관리자 권한 필요 없음^) ...
  winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
  call :refreshpath
  call :findpy
)
if not defined PY (
  echo     파이썬을 찾지 못했습니다. 이 창을 닫고 Setup.bat 을 다시 실행하세요.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo     %%v

echo.
echo [2/2] MemoDesk 를 켭니다. 화면 맨 위 "시작하기 전에" 안내를 따라 Claude Code 설치와 로그인을 마치세요.
call "%~dp0MemoDesk.bat"
exit /b

:findpy
rem 파이썬 3.10 이상 찾기 — python → py -3 → 기본 설치 자리. Windows 스토어 바로가기(python 이라고 치면 스토어가 열리는 것)는 실행이 실패해 걸러진다
set "PY="
python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set "PY=python" && goto :eof
py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set "PY=py -3" && goto :eof
for %%V in (313 312 311 310) do if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" && goto :eof
goto :eof

:refreshpath
rem 방금 설치한 프로그램이 이 창에서도 보이게 PATH 를 다시 읽는다(새 창을 열지 않아도 되게)
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
goto :eof
