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
    """점검 결과. 몇 초 걸리므로 CACHE_SECONDS 동안 다시 쓴다(화면은 2초마다 묻는다)."""
    with _lock:
        if not force and _cache["data"] and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
    items = []
    version = ".".join(map(str, sys.version_info[:3]))
    items.append({"id": "python", "name": "파이썬", "required": True, "ok": sys.version_info >= (3, 10),
                  "detail": f"{version} · {sys.executable}", "action": ""})
    claude = find_claude()
    if claude:
        code, text = _run([claude, "--version"], timeout=30)
        cli = {"ok": code == 0, "detail": text.strip().splitlines()[0] if code == 0 and text.strip() else f"실행 실패: {text.strip()[:120]}"}
    else:
        cli = {"ok": False, "detail": "설치되어 있지 않습니다"}
    items.append({"id": "claude_cli", "name": "Claude Code CLI", "required": True, **cli,
                  "action": "" if cli["ok"] else "install_claude",
                  "help": "AI 가 메모를 처리하는 프로그램입니다. 버튼을 누르면 공식 설치 명령이 새 창에서 돕니다(관리자 권한 필요 없음)."})
    login = _claude_login(claude) if cli["ok"] else {"ok": False, "detail": "CLI 를 먼저 설치하세요"}
    items.append({"id": "claude_login", "name": "클로드 계정 로그인", "required": True, **login,
                  "action": "" if login["ok"] or not cli["ok"] else "login_claude",
                  "help": "Pro · Max · Team · Enterprise · Console 계정이 필요합니다(무료 플랜은 안 됩니다). 버튼을 누르면 새 창이 뜨고 브라우저에서 로그인합니다."})
    git = find_git()
    items.append({"id": "git", "name": "Git for Windows" if IS_WINDOWS else "git", "required": False, "ok": bool(git),
                  "detail": git or "설치되어 있지 않습니다",
                  "action": "" if git or not IS_WINDOWS else "install_git",
                  "help": "권장. 없으면 클로드가 PowerShell 로 명령을 돌려 '지울 파일 보관 폴더로 옮기기'가 막힐 수 있습니다."})
    data = {"ready": all(i["ok"] for i in items if i["required"]), "items": items, "claude": claude or "",
            "winget": bool(shutil.which("winget")), "windows": IS_WINDOWS}
    with _lock:
        _cache.update(at=time.monotonic(), data=data)
    return data


def _console(title: str, script: str) -> None:
    """보이는 새 PowerShell 창에서 돌린다. 끝나도 창은 남겨 결과를 읽게 한다."""
    full = (f"$Host.UI.RawUI.WindowTitle = '{title}'; {script}; "
            "Write-Host ''; Write-Host '끝났으면 이 창을 닫고 MemoDesk 화면에서 [다시 확인]을 누르세요.' -ForegroundColor Cyan")
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", full],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


def run_action(action: str) -> dict:
    """버튼 — 고정된 명령만 돈다. Windows 가 아니면 손으로 칠 명령을 돌려준다."""
    with _lock:
        _cache["data"] = None   # 끝난 뒤 [다시 확인] 이 새로 재게
    claude = find_claude() or "claude"
    if action == "install_claude":
        if not IS_WINDOWS:
            return {"manual": CLAUDE_INSTALL_SH}
        _console("Claude Code 설치", CLAUDE_INSTALL_PS)
        return {"opened": True}
    if action == "login_claude":
        if not IS_WINDOWS:
            return {"manual": "claude auth login"}
        _console("클로드 로그인", f"& '{claude}' auth login")
        return {"opened": True}
    if action == "install_git":
        if not IS_WINDOWS:
            return {"manual": "OS 의 패키지 관리자로 git 을 설치하세요"}
        if not shutil.which("winget"):
            return {"manual": "https://git-scm.com/downloads/win 에서 받아 설치하세요(winget 이 없습니다)"}
        _console("Git for Windows 설치", "winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements")
        return {"opened": True}
    if action == "try_call":
        found = find_claude()
        if not found:
            raise ValueError("Claude Code CLI 가 없습니다")
        code, text = _run([found, "-p", "ok 라고만 답해", "--model", "haiku", "--output-format", "json"], timeout=180)
        try:
            data = json.loads(text[text.index("{"):]) if "{" in text else {}
        except ValueError:
            data = {}
        if code == 0 and not data.get("is_error"):
            return {"ok": True, "detail": f"불러짐 — 답: {str(data.get('result', '')).strip()[:40]}"}
        return {"ok": False, "detail": (str(data.get("result") or text).strip())[:300]}
    raise ValueError(f"모르는 동작: {action}")
