"""처음 쓰기 전에 갖출 것 — **쓸 AI 고르기** → (Gemini 면 Node.js) → AI 프로그램 설치 → 계정 로그인. 점검과 버튼.

2026-10-14 사용자 요청 — "AI 는 많잖아? 목록을 주고 어떤 AI 를 쓸지 고르고, 로그인하고, CLI 설치까지".
AI 마다 다른 것(설치 명령 · 계정 · 로그인 확인 방법)은 providers.py 에 있다.

| 항목 | 필요 | 확인 | 버튼 |
|---|---|---|---|
| 기본 실행 환경(Python) | 꼭 | 지금 도는 서버 | — (없으면 서버가 안 켜진다 — `Setup.bat` 이 먼저 깐다) |
| 쓸 AI 고르기 | 꼭 | config.json 의 `ai` | AI 카드 |
| Node.js | 꼭(Gemini · winget 없는 PC 의 Copilot) | `node` | winget · 없으면 nodejs.org 공식 설치 파일 |
| AI 프로그램 | 꼭 | `<cli> --version` | 공식 설치 명령 창 |
| AI 계정 로그인 | 꼭 | Claude `auth status` · Codex `login status` · Gemini 는 확인 명령이 없어 한 번 불러 본다 | 로그인 창 |
| 보조 도구(Git) | 있으면 좋음(Claude 만) | `git` | winget · 없으면 GitHub 공식 설치 파일 |

- 설치 · 로그인은 **보이는 새 창**에서 돈다(사람이 진행 상황과 브라우저 로그인을 본다). 버튼이 부르는 명령은 여기 고정된 것뿐이다.
- 설치 직후에는 이 서버의 PATH 에 새 프로그램이 없다 — 기본 설치 자리도 찾고(`providers.find_cli`), 프로그램을 부를 때는
  그 자리들을 PATH 앞에 붙인다(`tool_env`). Gemini 의 npm 실행 파일은 node 를 PATH 에서 찾는다.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from memodesk import config, providers
from memodesk.notes import KST

IS_WINDOWS = os.name == "nt"
CACHE_SECONDS = 60

_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


def tool_env() -> dict:
    """AI 프로그램 · node · git 을 부를 환경. 설치 직후에도 찾게 기본 설치 자리를 PATH 앞에 붙인다."""
    extra = [Path.home() / ".local" / "bin"]
    if IS_WINDOWS:
        if os.environ.get("APPDATA"):
            extra.append(Path(os.environ["APPDATA"]) / "npm")
        extra.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs")
        extra.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd")
    node = providers.find_node()
    if node:
        extra.insert(0, Path(node).parent)
    path = os.pathsep.join([str(p) for p in extra if p.is_dir()] + [os.environ.get("PATH", "")])
    return {**os.environ, "PATH": path}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                             env=tool_env(), creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return out.returncode, (out.stdout or "") + (out.stderr or "")


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


def needs_node(ai: str) -> bool:
    """Node.js 단계가 필요한가 — Gemini 는 늘(npm 으로만 깐다), Copilot 은 winget 이 없을 때(npm 으로 깐다)."""
    flag = providers.get(ai).get("needs_node")
    return flag is True or (flag == "no_winget" and not shutil.which("winget"))


def chosen() -> str:
    ai = config.load().get("ai") or ""
    return ai if ai in providers.PROVIDERS else ""


def choose(pid: str) -> None:
    providers.get(pid)
    config.update(ai=pid)
    with _lock:
        _cache["data"] = None


# ── 로그인 확인 — AI 마다 다르다 ──────────────────────────────────────────────

def _login_status(pid: str, cli: str) -> dict:
    kind = providers.get(pid)["status"]
    if kind == "claude_auth":
        code, text = _run([cli, "auth", "status"], timeout=30)
        try:
            data = json.loads(text[text.index("{"):]) if "{" in text else {}
        except ValueError:
            data = {}
        if data.get("loggedIn"):
            who = data.get("email") or data.get("orgName") or ""
            plan = data.get("subscriptionType") or data.get("authMethod") or ""
            return {"ok": True, "detail": " · ".join(x for x in (who, plan) if x) or "로그인됨"}
        return {"ok": False, "detail": "로그인되어 있지 않습니다" if data else f"로그인 상태를 읽지 못했습니다: {text.strip()[:120]}"}
    if kind == "codex_login":
        code, text = _run([cli, "login", "status"], timeout=30)
        line = next((l.strip() for l in text.splitlines() if l.strip()), "")
        ok = code == 0 and "logged in" in text.lower() and "not logged in" not in text.lower()
        return {"ok": ok, "detail": line or ("로그인됨" if ok else "로그인되어 있지 않습니다")}
    if kind == "cursor_status":
        code, text = _run([cli, "status"], timeout=30)
        low = text.lower()
        if code == 0 and ("logged in" in low or "authenticated" in low) and "not logged in" not in low and "not authenticated" not in low:
            line = next((l.strip() for l in text.splitlines() if l.strip()), "로그인됨")
            return {"ok": True, "detail": line[:120]}
        return {"ok": False, "detail": "로그인되어 있지 않습니다" if code == 0 or "not" in low else f"로그인 상태를 읽지 못했습니다: {text.strip()[:120]}"}
    # real_call — 확인 명령이 없다. 마지막으로 실제 호출이 된 시각을 기억해 둔다
    verified = (config.load().get("verified") or {}).get(pid)
    if verified:
        return {"ok": True, "detail": f"확인됨 · {verified[:16].replace('T', ' ')}"}
    return {"ok": False, "detail": "로그인한 뒤 [로그인 확인]을 누르세요(한 번 실제로 불러 봅니다)"}


def check(force: bool = False) -> dict:
    """점검 결과. 몇 초 걸리므로 CACHE_SECONDS 동안 다시 쓴다. 이름 · 설명은 개발자가 아닌 사람도 읽게 쉬운 말로."""
    with _lock:
        if not force and _cache["data"] and time.monotonic() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
    ai = chosen()
    items = []
    version = ".".join(map(str, sys.version_info[:3]))
    items.append({"id": "python", "name": "기본 실행 환경 (Python)", "required": True, "ok": sys.version_info >= (3, 10),
                  "detail": f"Python {version}", "action": "", "help": ""})
    info = providers.PROVIDERS.get(ai)
    items.append({"id": "ai", "name": "쓸 AI 고르기", "required": True, "ok": bool(info),
                  "detail": f"{info['name']} ({info['company']})" if info else "아직 고르지 않았습니다",
                  "action": "choose", "help": "메모를 처리할 AI 를 고릅니다. 나중에 바꿀 수 있습니다."})
    if info:
        node_min = info.get("node_min", 20)
        if needs_node(ai):
            node = providers.find_node()
            node_ok = False
            if node:
                code, text = _run([node, "--version"], timeout=20)
                try:
                    node_ok = code == 0 and int(text.strip().lstrip("v").split(".")[0]) >= node_min
                except ValueError:
                    node_ok = False
                node_detail = f"설치됨 · {text.strip()}" + ("" if node_ok else f" — {node_min} 이상이 필요합니다")
            else:
                node_detail = "아직 설치되지 않았습니다"
            items.append({"id": "node", "name": f"Node.js ({info['name']} 설치에 필요)", "required": True, "ok": node_ok, "detail": node_detail,
                          "action": "" if node_ok else "install_node",
                          "help": f"{info['cli_name']} 를 설치하는 데 필요한 프로그램입니다. 설치 중 관리자 확인 창이 뜨면 '예'를 누르세요."})
        cli = providers.find_cli(ai)
        if cli:
            code, text = _run([cli, "--version"], timeout=30)
            first = text.strip().splitlines()[0] if text.strip() else ""
            cli_state = {"ok": code == 0, "detail": f"설치됨 · {first}" if code == 0 else f"설치는 되어 있지만 실행이 안 됩니다: {text.strip()[:120]}"}
        else:
            cli_state = {"ok": False, "detail": "아직 설치되지 않았습니다"}
        blocked = needs_node(ai) and not items[-1]["ok"]
        items.append({"id": "cli", "name": f"AI 프로그램 ({info['cli_name']})", "required": True, **cli_state,
                      "action": "" if cli_state["ok"] or blocked else "install_cli",
                      "help": "Node.js 를 먼저 설치하세요." if blocked else
                              "메모를 읽고 일하는 AI 프로그램입니다. [설치하기]를 누르면 새 창에서 설치됩니다(1~3분)."})
        login = _login_status(ai, cli) if cli_state["ok"] else {"ok": False, "detail": "AI 프로그램을 먼저 설치하세요"}
        real_call = info["status"] == "real_call"
        items.append({"id": "login", "name": f"AI 계정 로그인 ({info['name']})", "required": True, **login,
                      "action": "" if login["ok"] or not cli_state["ok"] else "login",
                      "action2": "verify_login" if real_call and cli_state["ok"] and not login["ok"] else "",
                      "help": info["plan"] + " [로그인하기]를 누르면 새 창이 열립니다 — " + info["login_hint"]})
        if ai == "claude":
            git = find_git()
            items.append({"id": "git", "name": "보조 도구 (Git)", "required": False, "ok": bool(git),
                          "detail": "설치됨" if git else "아직 설치되지 않았습니다",
                          "action": "" if git or not IS_WINDOWS else "install_git",
                          "help": "있으면 AI 가 더 안정적으로 일합니다(파일 옮기기 등). 없어도 쓸 수는 있습니다. "
                                  "설치 중 관리자 확인 창이 뜨면 '예'를 누르세요."})
    cards = [{"id": pid, "name": p["name"], "company": p["company"], "plan": p["plan"], "pitch": p["pitch"],
              "installed": bool(providers.find_cli(pid)), "chosen": pid == ai} for pid, p in
             ((pid, providers.PROVIDERS[pid]) for pid in providers.ORDER)]
    data = {"ready": all(i["ok"] for i in items if i["required"]), "items": items, "ai": ai, "providers": cards,
            "winget": bool(shutil.which("winget")), "windows": IS_WINDOWS}
    with _lock:
        _cache.update(at=time.monotonic(), data=data)
    return data


# ── 버튼 ─────────────────────────────────────────────────────────────────────

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
                     env=tool_env(), creationflags=subprocess.CREATE_NEW_CONSOLE)


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
# Node.js LTS — winget 이 없으면 nodejs.org 의 배포 목록에서 최신 LTS 의 64비트 MSI 를 받아 실행한다(관리자 확인 창이 뜰 수 있다)
NODE_FROM_NODEJS_ORG = (
    "$all = Invoke-RestMethod 'https://nodejs.org/dist/index.json'; "
    "$lts = $all | Where-Object { $_.lts -and ($_.files -contains 'win-x64-msi') } | Select-Object -First 1; "
    "if (-not $lts) { throw 'Node.js 설치 파일을 찾지 못했습니다 — https://nodejs.org 에서 LTS 를 직접 받아 주세요' }; "
    "$name = 'node-' + $lts.version + '-x64.msi'; $file = Join-Path $env:TEMP $name; "
    "Write-Host ('내려받는 중: ' + $name + ' ...'); "
    "Invoke-WebRequest ('https://nodejs.org/dist/' + $lts.version + '/' + $name) -OutFile $file -UseBasicParsing; "
    "Write-Host '설치 중 ... (관리자 확인 창이 뜨면 예)'; "
    "$p = Start-Process msiexec.exe -ArgumentList '/i', ('\"' + $file + '\"'), '/passive', '/norestart' -Wait -PassThru; "
    "if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw ('설치 프로그램이 오류 코드 ' + $p.ExitCode + ' 로 끝났습니다') }"
)
NODE_FROM_WINGET = "winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements"
# npm 은 설치 직후 PATH 에 없을 수 있다 — 기본 자리를 직접 찾는다
NPM_FIND = ("$npm = (Get-Command npm -ErrorAction SilentlyContinue).Source; "
            "if (-not $npm) { $npm = Join-Path $env:ProgramFiles 'nodejs\\npm.cmd' }; "
            "if (-not (Test-Path $npm)) { throw 'npm 을 찾지 못했습니다 — Node.js 를 먼저 설치하세요' }; ")


def run_action(action: str, value: str = "") -> dict:
    """버튼 — 고정된 명령만 돈다. Windows 가 아니면 손으로 칠 명령을 돌려준다."""
    with _lock:
        _cache["data"] = None   # 끝난 뒤 새로 재게
    if action == "choose":
        choose(value)
        return {"chosen": value}
    if action in ("install_git", "install_node"):
        if not IS_WINDOWS:
            return {"manual": "OS 의 패키지 관리자로 설치하세요"}
        has_winget = bool(shutil.which("winget"))
        if action == "install_git":
            _console("Git 설치", "보조 도구(Git)를 설치합니다. 몇 분 걸릴 수 있습니다. 끝날 때까지 이 창을 닫지 마세요.",
                     GIT_FROM_WINGET if has_winget else GIT_FROM_GITHUB)
        else:
            _console("Node.js 설치", "Node.js 를 설치합니다. 몇 분 걸릴 수 있습니다. 끝날 때까지 이 창을 닫지 마세요.",
                     NODE_FROM_WINGET if has_winget else NODE_FROM_NODEJS_ORG)
        return {"opened": True}
    ai = chosen()
    if not ai:
        raise ValueError("먼저 쓸 AI 를 고르세요")
    info = providers.get(ai)
    cli = providers.find_cli(ai) or info["cli"]
    if action == "install_cli":
        if not IS_WINDOWS:
            return {"manual": info["install_sh"]}
        if ai == "gemini":
            script = NPM_FIND + "& $npm install -g @google/gemini-cli"
        elif ai == "copilot":
            script = ("winget install -e --id GitHub.Copilot --accept-source-agreements --accept-package-agreements"
                      if shutil.which("winget") else NPM_FIND + "& $npm install -g @github/copilot")
        else:
            script = info["install_ps"]
        _console(f"{info['cli_name']} 설치", f"AI 프로그램({info['cli_name']})을 설치합니다. 1~3분 걸립니다. 끝날 때까지 이 창을 닫지 마세요.", script)
        return {"opened": True}
    if action == "login":
        if not IS_WINDOWS:
            return {"manual": " ".join([info["cli"], *info["login_args"]])}
        args = " ".join(info["login_args"])
        _console(f"{info['name']} 로그인", info["login_hint"], f"& '{_ps_quote(cli)}' {args}".strip())
        return {"opened": True}
    if action in ("try_call", "verify_login"):
        found = providers.find_cli(ai)
        if not found:
            raise ValueError(f"AI 프로그램({info['cli_name']})이 없습니다")
        ok, detail = _ping(ai, found)
        if ok and info["status"] == "real_call":
            verified = dict(config.load().get("verified") or {})
            verified[ai] = datetime.now(KST).isoformat(timespec="seconds")
            config.update(verified=verified)
        return {"ok": ok, "detail": detail}
    raise ValueError(f"모르는 동작: {action}")


def _ping(ai: str, cli: str) -> tuple[bool, str]:
    """AI 를 한 번 짧게 불러 실제로 답하는지 본다(가장 싼 방법으로)."""
    if ai == "claude":
        cmd = [cli, "-p", "ok 라고만 답해", "--model", "haiku", "--output-format", "json"]
    elif ai == "codex":
        cmd = [cli, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "ok 라고만 답해"]
    elif ai == "copilot":
        cmd = [cli, "-p", "ok", "-s"]
    elif ai == "cursor":
        cmd = [cli, "-p", "ok", "--output-format", "json"]
    else:
        cmd = [cli, "-p", "ok 라고만 답해", "--output-format", "json"]
    code, text = _run(cmd, timeout=180)
    if code == 0:
        return True, "AI 가 정상으로 답했습니다"
    return False, text.strip()[-300:] or f"종료 코드 {code}"


def pick_folder(title: str = "AI 가 고칠 폴더를 고르세요") -> str:
    """폴더 고르기 창(Windows) — 경로를 손으로 치지 않게(2026-10-14, 개발자가 아닌 사람도 쓴다). 취소하면 빈 문자열.

    브라우저 뒤에 숨지 않게 **화면에 실제로 띄운** 맨 위 고정 창(투명)을 주인으로 준다. 실측(2026-10-14) — 주인 창을 만들기만 하고
    띄우지 않았더니 맨 위 고정이 안 먹어 대화상자가 안 보인 채로 기다렸다(사용자가 두 번 눌러 둘 다 숨어 있었다)."""
    if not IS_WINDOWS:
        raise ValueError("폴더 고르기는 Windows 에서만 됩니다 — 경로를 직접 적어 주세요")
    if not _picker_lock.acquire(blocking=False):   # 여러 번 눌러도 창은 하나 — 숨은 창이 쌓이지 않게
        raise ValueError("폴더 고르기 창이 이미 열려 있습니다 — 작업 표시줄에서 그 창을 찾아 고르거나 취소하세요")
    try:
        return _pick_folder(title)
    finally:
        _picker_lock.release()


_picker_lock = threading.Lock()

# 탐색기 모양 폴더 선택 창(Windows Vista+ 공통 파일 대화상자, IFileOpenDialog + FOS_PICKFOLDERS) — 브라우저의 파일 선택 창과
# 같은 모양이다. 2026-10-14 사용자 요청: 예전 트리 모양(FolderBrowserDialog)이 아니라 "파일 선택할 때 뜨는 창처럼".
# 브라우저 자체의 폴더 선택(webkitdirectory · showDirectoryPicker)은 보안상 전체 경로를 주지 않아 쓸 수 없다.
_PICKER_CS = r"""
using System;
using System.Runtime.InteropServices;
public static class MemoDeskFolderPicker {
  [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogRCW {}
  [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFileDialog {
    [PreserveSig] int Show(IntPtr parent);
    void SetFileTypes(uint cFileTypes, IntPtr rgFilterSpec);
    void SetFileTypeIndex(uint iFileType);
    void GetFileTypeIndex(out uint piFileType);
    void Advise(IntPtr pfde, out uint pdwCookie);
    void Unadvise(uint dwCookie);
    void SetOptions(uint fos);
    void GetOptions(out uint pfos);
    void SetDefaultFolder(IShellItem psi);
    void SetFolder(IShellItem psi);
    void GetFolder(out IShellItem ppsi);
    void GetCurrentSelection(out IShellItem ppsi);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
    void GetResult(out IShellItem ppsi);
  }
  [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItem {
    void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
    void GetParent(out IShellItem ppsi);
    void GetDisplayName(uint sigdnName, out IntPtr ppszName);
  }
  public static string Pick(string title, string okLabel, IntPtr owner) {
    IFileDialog dlg = (IFileDialog)new FileOpenDialogRCW();
    dlg.SetOptions(0x20 | 0x40 | 0x800);   // FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
    dlg.SetTitle(title);
    dlg.SetOkButtonLabel(okLabel);
    if (dlg.Show(owner) != 0) return "";   // 취소
    IShellItem item; dlg.GetResult(out item);
    IntPtr p; item.GetDisplayName(0x80058000, out p);   // SIGDN_FILESYSPATH
    string path = Marshal.PtrToStringUni(p); Marshal.FreeCoTaskMem(p);
    return path;
  }
}
"""


def picker_script(title: str) -> str:
    """폴더 선택 창을 띄우는 PowerShell. 탐색기 모양 창을 만들지 못하면(아주 옛 Windows 등) 예전 트리 모양 창으로 대신한다.
    브라우저 뒤에 숨지 않게 화면에 실제로 띄운 맨 위 고정 창(투명)을 주인으로 준다 — 만들기만 하고 띄우지 않으면
    맨 위 고정이 안 먹어 창이 안 보인 채로 기다렸다(실측 2026-10-14)."""
    return (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$owner = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; ShowInTaskbar = $false; "
        "Opacity = 0; FormBorderStyle = 'None'; StartPosition = 'CenterScreen'; Width = 1; Height = 1}; "
        "$owner.Show(); $owner.Activate(); $picked = ''; "
        f"try {{ Add-Type -TypeDefinition @'\n{_PICKER_CS}\n'@ -Language CSharp; "
        f"$picked = [MemoDeskFolderPicker]::Pick('{_ps_quote(title)}', '이 폴더 선택', $owner.Handle) }} "
        "catch { $d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$d.Description = '{_ps_quote(title)}'; $d.ShowNewFolderButton = $true; "
        "if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $picked = $d.SelectedPath } }; "
        "$owner.Close(); [Console]::OutputEncoding = [Text.Encoding]::UTF8; [Console]::Out.Write($picked)"
    )


def _pick_folder(title: str) -> str:
    # C# 코드에 따옴표 · 줄바꿈이 많아 명령줄 따옴표 대신 -EncodedCommand(UTF-16 base64)로 넘긴다
    encoded = base64.b64encode(picker_script(title).encode("utf-16-le")).decode("ascii")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-STA", "-EncodedCommand", encoded], capture_output=True,
                             timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("폴더 고르기 창이 너무 오래 열려 있었습니다") from exc
    return out.stdout.decode("utf-8", errors="replace").strip()
