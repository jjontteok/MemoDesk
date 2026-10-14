"""AI 계정 바꾸기 — 계정마다 폴더를 따로 둔다(`data/accounts/<AI>/<이름>/`).

로그아웃 → 다시 로그인으로 바꾸면 이 PC 의 다른 프로그램(터미널의 Claude Code 등)까지 같이 바뀐다.
그래서 계정 폴더를 알려 주는 환경 변수를 MemoDesk 가 띄우는 AI 에만 넣는다(공식 문서로 확인한 것만):

| AI | 환경 변수 | 근거 |
|---|---|---|
| Claude | `CLAUDE_CONFIG_DIR` | "Each directory has its own settings, session history, and claude.ai login" |
| Codex | `CODEX_HOME` | 로그인(auth.json)이 그 폴더에 저장된다 |
| Gemini | `GEMINI_CLI_HOME` | 그 아래 `.gemini/` 에 로그인 · 설정을 둔다 |

Copilot 은 Windows 에서 로그인을 **Windows 자격 증명 관리자**(PC 에 하나)에 두고, Cursor 는 어디 두는지 확인하지 못했다 —
둘은 계정을 여러 개 두지 않고 [다시 로그인]으로 바꾼다(그 PC 의 그 AI 계정이 같이 바뀐다).
이름이 빈 값 = 기본 계정(환경 변수를 넣지 않는다 — 이 PC 에 원래 로그인한 계정).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from memodesk import config, providers

ENV_VAR = {"claude": "CLAUDE_CONFIG_DIR", "codex": "CODEX_HOME", "gemini": "GEMINI_CLI_HOME"}
NAME_RE = re.compile(r"^[0-9A-Za-z가-힣_-]{1,30}$")


def root(ai: str) -> Path:
    return config.DATA_DIR / "accounts" / ai


def supports(ai: str) -> bool:
    return ai in ENV_VAR


def names(ai: str) -> list[str]:
    folder = root(ai)
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if supports(ai) and folder.is_dir() else []


def current(ai: str) -> str:
    """지금 쓰는 계정 이름. 폴더가 없어졌으면 기본으로 본다."""
    name = (config.load().get("accounts") or {}).get(ai, "")
    return name if name and name in names(ai) else ""


def folder(ai: str) -> Path | None:
    """지금 계정의 폴더. 기본 계정이면 None."""
    name = current(ai)
    return root(ai) / name if name else None


def env_for(ai: str) -> dict:
    """그 AI 를 부를 때 덧붙일 환경 변수. 기본 계정이면 비어 있다."""
    home = folder(ai)
    return {ENV_VAR[ai]: str(home)} if home else {}


def label(ai: str) -> str:
    return current(ai) or "기본 계정"


def verified_key(ai: str) -> str:
    """로그인 확인 기록(config.verified)의 키 — 계정마다 따로."""
    name = current(ai)
    return f"{ai}@{name}" if name else ai


def use(ai: str, name: str) -> None:
    providers.get(ai)
    if name and name not in names(ai):
        raise ValueError(f"없는 계정: {name}")
    picked = dict(config.load().get("accounts") or {})
    picked[ai] = name
    config.update(accounts=picked)


def create(ai: str, name: str) -> None:
    """새 계정 폴더를 만들고 그 계정으로 바꾼다(로그인은 그다음 창에서)."""
    providers.get(ai)
    if not supports(ai):
        raise ValueError(f"{providers.get(ai)['name']} 는 계정을 여러 개 둘 수 없습니다 — [다시 로그인]으로 바꿉니다")
    if not NAME_RE.match(name):
        raise ValueError("계정 이름은 한글 · 영문 · 숫자 · _ · - 로 30자까지 적습니다")
    target = root(ai) / name
    if target.exists():
        raise ValueError(f"이미 있는 이름입니다: {name}")
    target.mkdir(parents=True)
    use(ai, name)


def delete(ai: str, name: str, busy_homes: set[str] = frozenset()) -> None:
    """계정을 지운다 — 폴더째(이 PC 에 저장된 로그인 정보까지). 되돌릴 수 없어 화면이 먼저 묻는다(2026-10-14 사용자 요청).
    busy_homes = 도는 작업이 쓰는 계정 폴더 — 그 폴더는 지우지 않는다. 지금 쓰던 계정이면 기본 계정으로 돌아간다."""
    if name not in names(ai):
        raise ValueError(f"없는 계정: {name}")
    target = (root(ai) / name).resolve()
    if target.parent != root(ai).resolve():
        raise ValueError("MemoDesk 계정 폴더가 아니다")
    if str(root(ai) / name) in busy_homes:
        raise ValueError("이 계정으로 도는 작업이 있습니다 — 끝난 뒤에 지우세요")
    if current(ai) == name:
        use(ai, "")
    shutil.rmtree(target)


def state(ai: str) -> dict:
    return {"supported": supports(ai), "names": names(ai), "current": current(ai)}
