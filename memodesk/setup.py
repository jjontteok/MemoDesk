"""처음 쓰기 전에 갖출 것 — 점검과 설치 · 로그인 버튼.

| 항목 | 필요 | 확인 | 버튼 |
|---|---|---|---|
| 파이썬 3.10+ | 필수 | 지금 도는 서버 | — (없으면 서버가 안 켜진다 — `Setup.bat` 이 먼저 깐다) |
| Claude Code CLI | 필수 | `claude --version` | 공식 설치 명령(`irm https://claude.ai/install.ps1 \\| iex`) 창 |
| 클로드 로그인 | 필수 | `claude auth status`(JSON, 비용 없음) | `claude auth login` 창 |
| Git for Windows | 권장 | `git --version` | `winget install Git.Git` 창 |

- Claude Code 는 Pro · Max · Team · Enterprise · Console 계정이 있어야 한다(무료 플랜은 안 된다 — 공식 문서).
- Git for Windows 가 없으면 클로드가 Bash 대신 PowerShell 로 명령을 돌린다. MemoDesk 는 `Bash(mv:*)` 등만 허락하므로
  "지울 파일은 보관 폴더로 옮기기" 가 막힐 수 있다 — 그래서 권장.
- 설치 · 로그인은 **보이는 새 창**에서 돈다(사람이 진행 상황과 브라우저 로그인을 본다). 버튼이 부르는 명령은 여기 고정된 것뿐이다.
- 설치 직후에는 이 서버의 PATH 에 새 프로그램이 없다. 그래서 claude 는 PATH 말고 기본 설치 자리도 찾는다.
- `claude auth status` 는 로컬 기록만 본다. 실제로 불러지는지는 [실제로 불러 보기](Haiku 로 한 번, 비용 약 $0.01)로 확인한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"
CLAUDE_INSTALL_PS = "irm https://claude.ai/install.ps1 | iex"
CLAUDE_INSTALL_SH = "curl -fsSL https://claude.ai/install.sh | bash"
CACHE_SECONDS = 60

_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                             creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return out.returncode, (out.stdout or "") + (out.stderr or "")


def find_claude() -> str | None:
    """claude 실행 파일. PATH 에 없으면 공식 설치 자리(~/.local/bin)와 npm 전역 자리를 본다(설치 직후 대비)."""
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    candidates = [home / ".local" / "bin" / ("claude.exe" if IS_WINDOWS else "claude")]
    if IS_WINDOWS and os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "npm" / "claude.cmd")
    return next((str(p) for p in candidates if p.is_file()), None)


def find_git() -> str | None:
    found = shutil.which("git")
    if found:
        return found
    if IS_WINDOWS:   # 설치 직후 — 이 서버의 PATH 에는 아직 없다
        candidates = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd" / "git.exe"]
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Git" / "cmd" / "git.exe")
        return next((str(p) for p in candidates if p.is_file()), None)
    return None


def _claude_login(claude: str) -> dict:
    code, text = _run([claude, "auth", "status"], timeout=30)
    try:
        data = json.loads(text[text.index("{"):]) if "{" in text else {}
    except ValueError:
        data = {}
    if data.get("loggedIn"):
        who = data.get("email") or data.get("orgName") or ""
        plan = data.get("subscriptionType") or data.get("authMethod") or ""
        return {"ok": True, "detail": " · ".join(x for x in (who, plan) if x) or "로그인됨"}
    if data:
        return {"ok": False, "detail": "로그인되어 있지 않습니다"}
    return {"ok": False, "detail": f"로그인 상태를 읽지 못했습니다(종료 코드 {code}): {text.strip()[:120]}"}


def check(force: bool = False) -> dict:
    """점검 결과. 몇 초 걸리므로 CACHE_SECONDS 동안 다시 쓴다(화면은 자주 묻는다).
    이름 · 설명은 개발자가 아닌 사람도 읽게 쉬운 말로 쓴다(2026-10-14 사용자 요청)."""
    with _lock:
        if not force and _cache["data"] and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
    items = []
    version = ".".join(map(str, sys.version_info[:3]))
    items.append({"id": "python", "name": "기본 실행 환경 (Python)", "required": True, "ok": sys.version_info >= (3, 10),
                  "detail": f"Python {version}", "action": "",
                  "help": "MemoDesk 를 돌리는 프로그램입니다. 이 화면이 보이면 이미 준비된 것입니다."})
    claude = find_claude()
    if claude:
        code, text = _run([claude, "--version"], timeout=30)
        cli = {"ok": code == 0, "detail": f"설치됨 · {text.strip().splitlines()[0]}" if code == 0 and text.strip()
               else f"설치는 되어 있지만 실행이 안 됩니다: {text.strip()[:120]}"}
    else:
        cli = {"ok": False, "detail": "아직 설치되지 않았습니다"}
    items.append({"id": "claude_cli", "name": "AI 프로그램 (Claude Code)", "required": True, **cli,
                  "action": "" if cli["ok"] else "install_claude",
                  "help": "메모를 읽고 파일을 고치는 AI 입니다. [설치하기]를 누르면 새 창이 열리고 1~2분 안에 설치됩니다. "
                          "관리자 권한은 필요 없습니다."})
    login = _claude_login(claude) if cli["ok"] else {"ok": False, "detail": "AI 프로그램을 먼저 설치하세요"}
    items.append({"id": "claude_login", "name": "AI 계정 로그인 (Claude)", "required": True, **login,
                  "action": "" if login["ok"] or not cli["ok"] else "login_claude",
                  "help": "유료 Claude 계정(Pro · Max · Team · Enterprise)이 필요합니다. 무료 계정은 쓸 수 없습니다. "
                          "[로그인하기]를 누르면 브라우저가 열립니다 — 평소 쓰는 Claude 계정으로 로그인하고 '허용'을 누르세요."})
    git = find_git()
    items.append({"id": "git", "name": "보조 도구 (Git)", "required": False, "ok": bool(git),
                  "detail": "설치됨" if git else "아직 설치되지 않았습니다",
                  "action": "" if git or not IS_WINDOWS else "install_git",
                  "help": "있으면 AI 가 더 안정적으로 일합니다(파일 옮기기 등). 없어도 쓸 수는 있습니다. "
                          "[설치하기]를 누르면 설치 프로그램이 열립니다 — 관리자 확인 창이 뜨면 '예'를 누르세요."})
    data = {"ready": all(i["ok"] for i in items if i["required"]), "items": items, "claude": claude or "",
            "winget": bool(shutil.which("winget")), "windows": IS_WINDOWS}
    with _lock:
        _cache.update(at=time.monotonic(), data=data)
    return data


def _ps_quote(text: str) -> str:
    """PowerShell 작은따옴표 문자열 안에 넣을 수 있게."""
    return text.replace("'", "''")


def _console(title: str, intro: str, script: str) -> None:
    """보이는 새 PowerShell 창에서 돌린다 — 사람이 진행 상황을 본다. 실패하면 이유를 빨갛게 남기고 창을 둔다."""
    full = (f"$Host.UI.RawUI.WindowTitle = '{_ps_quote(title)}'; [Console]::OutputEncoding = [Text.Encoding]::UTF8; "
            f"Write-Host '{_ps_quote(intro)}' -ForegroundColor Cyan; Write-Host ''; "
            "$ProgressPreference = 'SilentlyContinue'; "
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
            f"try {{ {script}; Write-Host ''; "
            "Write-Host '끝났습니다. 이 창은 닫아도 됩니다. MemoDesk 화면이 자동으로 다시 확인합니다.' -ForegroundColor Green } "
            "catch { Write-Host ''; Write-Host ('문제가 생겼습니다: ' + $_.Exception.Message) -ForegroundColor Red; "
            "Write-Host '이 창의 내용을 캡처해 담당자에게 보내 주세요.' -ForegroundColor Yellow }")
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", full],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


# Git for Windows — winget 이 있으면 그것으로, 없으면(회사 PC · 옛 Windows 에 흔하다 — 실측: 이 작업 PC 에도 없었다)
# GitHub 공식 릴리스의 64비트 설치 파일을 받아 진행 막대가 보이게(/SILENT) 실행한다
GIT_FROM_GITHUB = (
    "$rel = Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest'; "
    "$asset = $rel.assets | Where-Object { $_.name -match '^Git-.*-64-bit\\.exe$' } | Select-Object -First 1; "
    "if (-not $asset) { throw '설치 파일을 찾지 못했습니다 — https://git-scm.com/downloads/win 에서 직접 받아 주세요' }; "
    "$file = Join-Path $env:TEMP $asset.name; Write-Host ('내려받는 중: ' + $asset.name + ' ...'); "
    "Invoke-WebRequest $asset.browser_download_url -OutFile $file -UseBasicParsing; "
    "Write-Host '설치 중 ... (관리자 확인 창이 뜨면 예)'; "
    "$p = Start-Process $file -ArgumentList '/SILENT','/NORESTART','/SUPPRESSMSGBOXES' -Wait -PassThru; "
    "if ($p.ExitCode -ne 0) { throw ('설치 프로그램이 오류 코드 ' + $p.ExitCode + ' 로 끝났습니다') }"
)
GIT_FROM_WINGET = "winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements"


def run_action(action: str) -> dict:
    """버튼 — 고정된 명령만 돈다. Windows 가 아니면 손으로 칠 명령을 돌려준다."""
    with _lock:
        _cache["data"] = None   # 끝난 뒤 새로 재게
    claude = find_claude() or "claude"
    if action == "install_claude":
        if not IS_WINDOWS:
            return {"manual": CLAUDE_INSTALL_SH}
        _console("Claude Code 설치", "AI 프로그램(Claude Code)을 설치합니다. 1~2분 걸립니다. 끝날 때까지 이 창을 닫지 마세요.",
                 CLAUDE_INSTALL_PS)
        return {"opened": True}
    if action in ("login_claude", "login_console"):
        how = "--console" if action == "login_console" else "--claudeai"
        if not IS_WINDOWS:
            return {"manual": f"claude auth login {how}"}
        _console("Claude 로그인", "브라우저가 열리면 Claude 계정으로 로그인하고 '허용'을 누르세요. 끝나면 이 창에 성공 메시지가 나옵니다.",
                 f"& '{_ps_quote(claude)}' auth login {how}")
        return {"opened": True}
    if action == "install_git":
        if not IS_WINDOWS:
            return {"manual": "OS 의 패키지 관리자로 git 을 설치하세요"}
        _console("Git 설치", "보조 도구(Git)를 설치합니다. 몇 분 걸릴 수 있습니다. 끝날 때까지 이 창을 닫지 마세요.",
                 GIT_FROM_WINGET if shutil.which("winget") else GIT_FROM_GITHUB)
        return {"opened": True}
    if action == "try_call":
        found = find_claude()
        if not found:
            raise ValueError("AI 프로그램(Claude Code)이 없습니다")
        code, text = _run([found, "-p", "ok 라고만 답해", "--model", "haiku", "--output-format", "json"], timeout=180)
        try:
            data = json.loads(text[text.index("{"):]) if "{" in text else {}
        except ValueError:
            data = {}
        if code == 0 and not data.get("is_error"):
            return {"ok": True, "detail": "AI 가 정상으로 답했습니다"}
        return {"ok": False, "detail": (str(data.get("result") or text).strip())[:300]}
    raise ValueError(f"모르는 동작: {action}")


def pick_folder(title: str = "AI 가 고칠 폴더를 고르세요") -> str:
    """폴더 고르기 창(Windows) — 경로를 손으로 치지 않게(2026-10-14, 개발자가 아닌 사람도 쓴다). 취소하면 빈 문자열.
    브라우저 뒤에 숨지 않게 맨 위에 뜨는 빈 창을 주인으로 준다."""
    if not IS_WINDOWS:
        raise ValueError("폴더 고르기는 Windows 에서만 됩니다 — 경로를 직접 적어 주세요")
    script = ("Add-Type -AssemblyName System.Windows.Forms; "
              "$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false}; "
              "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
              f"$d.Description = '{_ps_quote(title)}'; $d.ShowNewFolderButton = $true; "
              "if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { "
              "[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Console]::Out.Write($d.SelectedPath) }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                             timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("폴더 고르기 창이 너무 오래 열려 있었습니다") from exc
    return out.stdout.decode("utf-8", errors="replace").strip()
