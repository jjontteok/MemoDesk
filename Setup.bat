@echo off
rem MemoDesk 처음 설치 — 더블클릭. 파이썬이 없으면 설치한 뒤 MemoDesk 를 켠다.
rem AI 프로그램(Claude Code) · 로그인 · Git 은 켜진 화면의 환경 점검 창에서 버튼으로 설치한다(파이썬이 있어야 화면이 켜진다).
chcp 65001 >nul
title MemoDesk 설치
cd /d "%~dp0"

echo.
echo [1/2] 파이썬 확인
call :findpy
if defined PY goto :havepy
rem winget 이 있으면 그것으로, 없으면(회사 PC · 옛 Windows 에 흔하다) python.org 공식 설치 파일로. 둘 다 이 사용자에게만 — 관리자 권한 필요 없음
where winget >nul 2>&1
if not errorlevel 1 goto :py_winget
echo     파이썬 3.12 를 python.org 에서 내려받아 설치합니다. 1~3분 걸립니다 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $f=Join-Path $env:TEMP 'python-3.12.10-amd64.exe'; Invoke-WebRequest 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $f -UseBasicParsing; $p=Start-Process $f -ArgumentList '/passive','InstallAllUsers=0','PrependPath=1','InstallLauncherAllUsers=0','Include_test=0' -Wait -PassThru; exit $p.ExitCode"
goto :py_after
:py_winget
echo     파이썬 3.12 를 설치합니다 ^(winget^) ...
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
:py_after
call :refreshpath
call :findpy
if defined PY goto :havepy
echo     파이썬을 설치하지 못했습니다. 인터넷 연결을 확인하고 이 파일을 다시 실행하세요.
echo     그래도 안 되면 https://www.python.org/downloads/ 에서 직접 설치하세요("Add python.exe to PATH" 에 체크).
pause
exit /b 1
:havepy
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo     %%v

echo.
echo [2/2] MemoDesk 를 켭니다. 브라우저에 뜨는 "환경 점검" 창의 안내를 따라 버튼을 누르세요.
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
