"""쓸 수 있는 AI — 설치 · 로그인 · 로그인 확인 · 실행 방법을 AI 마다 한곳에 모은다.

사람은 환경 점검 창에서 하나를 고른다(`config.json` 의 `ai`). 2026-10-14 사용자 요청 — "AI 는 많잖아? 목록을 주고
어떤 AI 를 쓸지 고르고, 로그인하고, CLI 설치까지".

출처(추측으로 넣지 않는다):
- Claude Code — code.claude.com/docs/en/setup: Windows `irm https://claude.ai/install.ps1 | iex`, Pro · Max · Team · Enterprise ·
  Console 계정, `claude auth login` · `claude auth status`(JSON).
- Codex — github.com/openai/codex: Windows PowerShell 설치 스크립트 `https://chatgpt.com/codex/install.ps1`(받아지는 것 확인),
  ChatGPT Plus · Pro · Business · Edu · Enterprise 로 로그인. `codex login` · `codex login status` · `codex exec` 옵션은
  설치된 0.158.0 의 --help 로 확인.
- GitHub Copilot CLI — github.com/github/copilot-cli: Windows 지원, `winget install GitHub.Copilot` · `npm install -g @github/copilot`,
  Copilot 구독 필요. `copilot login` · `-p`(비대화형) · `-s`(답만) · `--allow-tool write` · `--deny-tool` · `--add-dir` 는
  `npx @github/copilot --help`(1.0.97)로 확인. **로그인 상태를 묻는 명령이 없다** — 한 번 불러 확인한다.
- Cursor CLI — cursor.com/docs/cli: Windows 네이티브 `irm 'https://cursor.com/install?win32=true' | iex`(스크립트를 읽어 보니
  `%LOCALAPPDATA%/cursor-agent/cursor-agent` 로 깔고 `agent` 별칭을 만든다), `login` · `status`, `-p --force --output-format json`
  ({type, subtype, is_error, result, …}).
- 지시문이 길고 여러 줄이라 Copilot · Cursor 에는 명령줄로 넘기지 않고 파일로 넘긴다(Windows 의 .cmd 실행 파일은 cmd.exe 를 거쳐
  줄바꿈 · 특수 문자가 깨진다).
- 넣지 않은 것: Qwen Code(무료 로그인이 2026-04-15 종료 — 알리바바 유료 플랜 · API 키 필요), OpenCode · Aider(AI 회사별 API 키를
  직접 넣어야 해 개발자가 아니면 어렵다).
- Gemini CLI — github.com/google-gemini/gemini-cli: `npm install -g @google/gemini-cli`(Node.js 20 이상 — npm engines),
  Google 로그인 무료(하루 1,000회). `-p`(stdin 뒤에 붙는다) · `--output-format json`({response, stats, error}) ·
  `--approval-mode auto_edit` · `--include-directories`. **로그인 상태를 묻는 명령이 없다** — 한 번 실제로 불러 확인한다.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

IS_WINDOWS = os.name == "nt"


def _home_bin(name: str) -> Path:
    return Path.home() / ".local" / "bin" / (f"{name}.exe" if IS_WINDOWS else name)


def _npm_bin(name: str) -> Path | None:
    if IS_WINDOWS and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "npm" / f"{name}.cmd"
    return None


PROVIDERS: dict[str, dict] = {
    "claude": {
        "name": "Claude", "company": "Anthropic", "cli": "claude", "cli_name": "Claude Code",
        "plan": "유료 Claude 계정(Pro · Max · Team · Enterprise)이 필요합니다. 무료 계정은 쓸 수 없습니다.",
        "pitch": "글쓰기 · 문서 정리 · 코드 모두 잘합니다. 지우기 · git 명령을 확실히 막을 수 있어 가장 안전합니다.",
        "install_ps": "irm https://claude.ai/install.ps1 | iex",
        "install_sh": "curl -fsSL https://claude.ai/install.sh | bash",
        "needs_node": False,
        "login_args": ["auth", "login", "--claudeai"],
        "login_hint": "브라우저가 열리면 Claude 계정으로 로그인하고 '허용'을 누르세요.",
        "status": "claude_auth",       # claude auth status (JSON)
        "extra_paths": [_home_bin("claude"), _npm_bin("claude")],
        "default_model": "", "model_hint": "비우면 Claude Code 기본 모델",
    },
    "codex": {
        "name": "ChatGPT (Codex)", "company": "OpenAI", "cli": "codex", "cli_name": "Codex CLI",
        "plan": "ChatGPT Plus · Pro · Business · Edu · Enterprise 계정이 필요합니다.",
        "pitch": "ChatGPT 를 쓰고 있다면 그 계정으로 씁니다. 폴더 밖에는 쓰지 못하는 보호 모드로 돕니다.",
        "install_ps": "irm https://chatgpt.com/codex/install.ps1 | iex",
        "install_sh": "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
        "needs_node": False,
        "login_args": ["login"],
        "login_hint": "브라우저가 열리면 ChatGPT 계정으로 로그인하세요.",
        "status": "codex_login",       # codex login status (글)
        "extra_paths": [_home_bin("codex"), _npm_bin("codex")],
        "default_model": "", "model_hint": "비우면 Codex 기본 모델",
    },
    "gemini": {
        "name": "Gemini", "company": "Google", "cli": "gemini", "cli_name": "Gemini CLI",
        "plan": "Google 계정으로 무료로 시작할 수 있습니다(하루 1,000회까지).",
        "pitch": "무료로 써 볼 수 있습니다. 설치하려면 Node.js 가 먼저 필요합니다(버튼으로 함께 설치).",
        "install_ps": "npm install -g @google/gemini-cli",
        "install_sh": "npm install -g @google/gemini-cli",
        "needs_node": True,
        "login_args": [],              # 그냥 gemini 를 켜면 로그인 방법을 묻는다 — 'Sign in with Google'
        "login_hint": "창에서 'Sign in with Google' 을 고르고 브라우저에서 로그인한 뒤, 창에 /quit 을 치고 닫으세요.",
        "status": "real_call",         # 로그인 확인 명령이 없다 — 실제로 한 번 불러 본다
        "extra_paths": [_npm_bin("gemini")],
        "default_model": "", "model_hint": "비우면 Gemini 기본(auto)",
    },
}
PROVIDERS["copilot"] = {
    "name": "GitHub Copilot", "company": "GitHub", "cli": "copilot", "cli_name": "Copilot CLI",
    "plan": "GitHub Copilot 구독이 필요합니다(요금제마다 쓸 수 있는 양이 다릅니다 — GitHub 요금제 안내 참고).",
    "pitch": "회사에서 GitHub Copilot 을 쓰고 있다면 그 계정으로 씁니다. 지우기 · git 명령을 막을 수 있습니다.",
    "install_ps": "", "install_sh": "npm install -g @github/copilot",   # Windows 는 winget, 없으면 npm(setup.py)
    "needs_node": "no_winget", "node_min": 20,
    "login_args": ["login"],
    "login_hint": "창에 나오는 코드를 브라우저의 GitHub 페이지에 넣고 승인하세요.",
    "status": "real_call",
    "extra_paths": [_npm_bin("copilot"),
                    (Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / "copilot.exe") if IS_WINDOWS and os.environ.get("LOCALAPPDATA") else None],
    "default_model": "", "model_hint": "비우면 Copilot 기본 모델",
}
PROVIDERS["cursor"] = {
    "name": "Cursor", "company": "Anysphere", "cli": "cursor-agent", "cli_name": "Cursor CLI",
    "plan": "Cursor 계정이 필요합니다(요금제마다 쓸 수 있는 양이 다릅니다).",
    "pitch": "Cursor 편집기를 쓰고 있다면 그 계정으로 씁니다.",
    "install_ps": "irm 'https://cursor.com/install?win32=true' | iex",
    "install_sh": "curl https://cursor.com/install -fsS | bash",
    "needs_node": False,
    "login_args": ["login"],
    "login_hint": "브라우저가 열리면 Cursor 계정으로 로그인하세요.",
    "status": "cursor_status",
    "extra_paths": [*(Path(os.environ["LOCALAPPDATA"]) / "cursor-agent" / n for n in ("cursor-agent.exe", "cursor-agent.cmd"))]
    if IS_WINDOWS and os.environ.get("LOCALAPPDATA") else [_home_bin("cursor-agent")],
    "default_model": "", "model_hint": "비우면 Cursor 기본 모델",
}
PROVIDERS["gemini"]["node_min"] = 20
ORDER = ("claude", "codex", "copilot", "cursor", "gemini")


def get(pid: str) -> dict:
    if pid not in PROVIDERS:
        raise ValueError(f"모르는 AI: {pid}")
    return PROVIDERS[pid]


def find_cli(pid: str) -> str | None:
    """CLI 실행 파일. PATH 에 없으면 설치 기본 자리를 본다(설치 직후 — 서버의 PATH 에는 아직 없다)."""
    info = get(pid)
    found = shutil.which(info["cli"])
    if found:
        return found
    return next((str(p) for p in info["extra_paths"] if p and p.is_file()), None)


def find_node() -> str | None:
    found = shutil.which("node")
    if found:
        return found
    if IS_WINDOWS:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            if base and (Path(base) / "nodejs" / "node.exe").is_file():
                return str(Path(base) / "nodejs" / "node.exe")
    return None
