"""AI CLI 호출 — Claude · Codex · Copilot · Cursor · Gemini. 모두 같은 모양으로 부른다: run_prompt(프롬프트, 결과 스키마, 결과 파일, 모델).

모든 호출이 여기를 지나므로 **걸린 시간과 토큰을 여기서 적는다**(`usage.record_call`). 실패해도 걸린 시간은 남긴다.

AI 마다 안전장치가 다르다(providers.py 출처 참고).
- Claude: `--permission-mode acceptEdits` + 거부 목록(rm · git …) + `--setting-sources project`. 지우기를 확실히 막는다.
- Codex: `--sandbox workspace-write` — 작업 폴더와 `--add-dir` 폴더 밖에는 못 쓴다(실측 2026-10-14, Windows 에서 파일 수정 확인).
  지우기 명령을 따로 막을 수는 없다 — 프롬프트로 금하고, 작업 전 백업 · 되돌림이 지킨다.
- Gemini: `--approval-mode auto_edit` — 파일 고치기만 자동 승인, 명령 실행은 승인되지 않는다. 결과 스키마 옵션이 없어
  JSON 만 쓰라고 시키고 답에서 JSON 을 꺼낸다.
- Copilot: 파일 쓰기만 허락, 셸 명령은 거부(지우기 · git 불가). 지시문은 파일로.
- Cursor: `--force` 로 파일 고치기를 확인 없이 적용. 셸 명령을 막는 옵션은 확인하지 못했다 — 백업 · 되돌림이 지킨다. 지시문은 파일로.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from memodesk import usage


def resolve_executable(name: str) -> str:
    """셸이 고르는 것과 같은 실행 파일을 고정한다. Windows 의 `CreateProcess` 는 PATH 를 셸과 다른 순서로 찾아
    같은 이름의 다른 설치본을 부를 수 있다(차시 작업대 실측 — 옛 standalone 코덱스가 돌아 새 모델을 거절했다)."""
    return shutil.which(name) or name


def _timed(provider: str, stage: str | None, model: str | None, call):
    started = time.monotonic()
    try:
        got, used_model = call()
    except BaseException as exc:
        usage.record_call(stage, provider, model, time.monotonic() - started, None, False, f"{type(exc).__name__}: {exc}")
        raise
    usage.record_call(stage, provider, model or used_model, time.monotonic() - started, got, True)
    return got


def _write(output_path: Path, data: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── Claude ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ClaudeClient:
    cli: str
    cwd: Path                      # 작업 폴더 = 프로젝트 경로. 그 폴더의 CLAUDE.md 를 클로드가 스스로 읽는다
    timeout_seconds: int = 2400
    permission_mode: str = "acceptEdits"
    # `acceptEdits` 는 작업 폴더 안의 `mkdir` · `mv` · `rm` 같은 파일 명령을 허용 목록과 상관없이 자동 허락한다(차시 작업대 실측).
    # 막아야 하는 것은 disallowed_tools 에 — 거부가 허용보다 앞선다
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    setting_sources: str = "project"   # 사용자 전역 설정의 허용 규칙을 물려받지 않는다
    add_dirs: tuple[str, ...] = ()
    effort: str = ""
    provider: str = "claude"

    def run_prompt(self, prompt: str, schema: Path, output_path: Path, model: str | None = None, stage: str | None = None):
        return _timed(self.provider, stage, model, lambda: self._run(prompt, schema, output_path, model))

    def _run(self, prompt: str, schema: Path, output_path: Path, model: str | None):
        command = [resolve_executable(self.cli)]
        if model:
            command += ["--model", model]
        if self.effort:
            command += ["--effort", self.effort]
        command += ["-p", "Execute the complete task described in stdin and return only the requested structured output.",
                    "--output-format", "json", "--json-schema", schema_text(schema),
                    "--permission-mode", self.permission_mode, "--setting-sources", self.setting_sources]
        if self.allowed_tools:
            command += ["--allowedTools", *self.allowed_tools]
        if self.disallowed_tools:
            command += ["--disallowedTools", *self.disallowed_tools]
        for folder in self.add_dirs:
            command += ["--add-dir", folder]
        completed = _call(command, prompt, self.cwd, self.timeout_seconds, "Claude Code CLI")
        result = parse_json_output(completed.stdout)
        if result.get("is_error") is True:
            raise RuntimeError(f"Claude Code CLI returned an error result\nresult: {result.get('result')}\nstderr: {completed.stderr}")
        structured = result.get("structured_output")
        if not isinstance(structured, dict):
            structured = json_object_in_text(result.get("result"))
        if structured is None:
            raise RuntimeError(f"Claude Code CLI did not return structured output\nstdout: {completed.stdout}")
        _write(output_path, structured)
        got = {k: v for k, v in (("usage", result.get("usage")), ("model_usage", result.get("modelUsage")),
                                 ("total_cost_usd", result.get("total_cost_usd"))) if v is not None}
        models = got.get("model_usage") or {}
        return got or None, (next(iter(models), None) if isinstance(models, dict) else None)


# ── Codex ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CodexClient:
    cli: str
    cwd: Path
    timeout_seconds: int = 2400
    add_dirs: tuple[str, ...] = ()
    effort: str = ""
    provider: str = "codex"

    def run_prompt(self, prompt: str, schema: Path, output_path: Path, model: str | None = None, stage: str | None = None):
        return _timed(self.provider, stage, model, lambda: self._run(prompt, schema, output_path, model))

    def _run(self, prompt: str, schema: Path, output_path: Path, model: str | None):
        command = [resolve_executable(self.cli), "exec"]
        if self.effort:
            command += ["-c", f'model_reasoning_effort="{self.effort}"']
        if model:
            command += ["--model", model]
        command += ["--ephemeral", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", str(self.cwd)]
        for folder in self.add_dirs:
            command += ["--add-dir", folder]
        command += ["--output-schema", str(schema), "--output-last-message", str(output_path), "-"]
        output_path.unlink(missing_ok=True)
        completed = _call(command, prompt, self.cwd, self.timeout_seconds, "Codex CLI")
        data = json_object_in_text(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
        if data is None:
            raise RuntimeError(f"Codex CLI did not return structured output\nstdout: {completed.stdout[-2000:]}")
        _write(output_path, data)
        tokens = None
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and isinstance(event.get("usage"), dict):
                tokens = event["usage"]
        return ({"usage": tokens} if tokens else None), None


# ── Gemini ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GeminiClient:
    cli: str
    cwd: Path
    timeout_seconds: int = 2400
    add_dirs: tuple[str, ...] = ()
    provider: str = "gemini"

    def run_prompt(self, prompt: str, schema: Path, output_path: Path, model: str | None = None, stage: str | None = None):
        return _timed(self.provider, stage, model, lambda: self._run(prompt, schema, output_path, model))

    def _run(self, prompt: str, schema: Path, output_path: Path, model: str | None):
        # 결과 스키마 옵션이 없다 — 스키마를 보여 주고 JSON 만 쓰게 한 뒤 답에서 꺼낸다
        prompt = (prompt + "\n\n## 마지막 답의 모양\n작업을 다 한 뒤 마지막 답에는 아래 JSON 스키마에 맞는 **JSON 객체 하나만** 쓴다"
                  "(설명 · 코드 블록 표시 없이).\n" + schema_text(schema))
        command = [resolve_executable(self.cli), "-p", "Follow the task given on stdin.", "--output-format", "json",
                   "--approval-mode", "auto_edit"]
        if model:
            command += ["--model", model]
        if self.add_dirs:
            command += ["--include-directories", ",".join(self.add_dirs)]
        completed = _call(command, prompt, self.cwd, self.timeout_seconds, "Gemini CLI")
        result = parse_json_output(completed.stdout)
        if result.get("error"):
            raise RuntimeError(f"Gemini CLI returned an error\nerror: {result.get('error')}\nstderr: {completed.stderr}")
        data = json_object_in_text(result.get("response"))
        if data is None:
            raise RuntimeError(f"Gemini CLI did not return a JSON answer\nresponse: {str(result.get('response'))[:2000]}")
        _write(output_path, data)
        return ({"stats": result.get("stats")} if result.get("stats") else None), None


# ── Copilot · Cursor — 지시문은 파일로 넘긴다 ────────────────────────────────
# 둘 다 지시문을 명령줄 인자(-p "…")로만 받는다. Windows 의 npm · 설치 스크립트 실행 파일은 .cmd 라 cmd.exe 를 거치는데,
# 여러 줄 · 특수 문자(% ^ & |)가 깨지고 길이도 8,191자로 막힌다. 그래서 지시문 전체를 파일에 쓰고 "이 파일을 읽고 하라" 만 넘긴다.

def _task_file(task_dir: Path, prompt: str, schema: Path) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"task-{time.strftime('%Y%m%d-%H%M%S')}.md"
    path.write_text(prompt + "\n\n## 마지막 답의 모양\n작업을 다 한 뒤 마지막 답에는 아래 JSON 스키마에 맞는 **JSON 객체 하나만** 쓴다"
                    "(설명 · 코드 블록 표시 없이).\n" + schema_text(schema) + "\n", encoding="utf-8")
    return path


def _pointer(path: Path) -> str:
    return (f"Read the task file at {path} completely and do exactly what it says. "
            "Your final answer must be only the JSON object described at the end of that file.")


@dataclass(frozen=True)
class CopilotClient:
    """GitHub Copilot CLI — `copilot -p … -s`. 파일 쓰기(write)만 허락하고 셸 명령은 허락하지 않는다(지우기 · git 을 못 한다).
    폴더는 작업 폴더(cwd)와 --add-dir 폴더만."""
    cli: str
    cwd: Path
    task_dir: Path
    timeout_seconds: int = 2400
    add_dirs: tuple[str, ...] = ()
    provider: str = "copilot"

    def run_prompt(self, prompt: str, schema: Path, output_path: Path, model: str | None = None, stage: str | None = None):
        return _timed(self.provider, stage, model, lambda: self._run(prompt, schema, output_path, model))

    def _run(self, prompt: str, schema: Path, output_path: Path, model: str | None):
        task = _task_file(self.task_dir, prompt, schema)
        command = [resolve_executable(self.cli), "-p", _pointer(task), "-s", "--allow-tool", "write",
                   "--deny-tool", "shell", "--add-dir", str(self.task_dir)]
        for folder in self.add_dirs:
            command += ["--add-dir", folder]
        if model:
            command += ["--model", model]
        completed = _call(command, "", self.cwd, self.timeout_seconds, "Copilot CLI")
        data = json_object_in_text(completed.stdout)
        if data is None:
            raise RuntimeError(f"Copilot CLI did not return a JSON answer\nstdout: {completed.stdout[-2000:]}")
        _write(output_path, data)
        return None, None


@dataclass(frozen=True)
class CursorClient:
    """Cursor CLI — `cursor-agent -p --force --output-format json`. --force 는 파일 고치기를 확인 없이 적용한다.
    셸 명령을 따로 막는 옵션은 확인하지 못했다 — 작업 전 백업 · 되돌림이 지킨다."""
    cli: str
    cwd: Path
    task_dir: Path
    timeout_seconds: int = 2400
    provider: str = "cursor"

    def run_prompt(self, prompt: str, schema: Path, output_path: Path, model: str | None = None, stage: str | None = None):
        return _timed(self.provider, stage, model, lambda: self._run(prompt, schema, output_path, model))

    def _run(self, prompt: str, schema: Path, output_path: Path, model: str | None):
        task = _task_file(self.task_dir, prompt, schema)
        command = [resolve_executable(self.cli), "-p", _pointer(task), "--force", "--output-format", "json"]
        if model:
            command += ["--model", model]
        completed = _call(command, "", self.cwd, self.timeout_seconds, "Cursor CLI")
        result = parse_json_output(completed.stdout)
        if result.get("is_error") is True:
            raise RuntimeError(f"Cursor CLI returned an error\nresult: {str(result.get('result'))[:2000]}")
        data = json_object_in_text(result.get("result"))
        if data is None:
            raise RuntimeError(f"Cursor CLI did not return a JSON answer\nresult: {str(result.get('result'))[:2000]}")
        _write(output_path, data)
        return None, None


# ── 공통 ────────────────────────────────────────────────────────────────────

def _call(command: list[str], prompt: str, cwd: Path, timeout: int, name: str) -> subprocess.CompletedProcess:
    try:
        completed = subprocess.run(command, input=prompt, text=True, capture_output=True, encoding="utf-8",
                                   errors="replace", cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{name} timed out in non-interactive mode (timeout_seconds: {timeout})") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed (exit {completed.returncode})\nstdout: {completed.stdout[-4000:]}\nstderr: {completed.stderr[-4000:]}")
    return completed


def schema_text(schema: Path) -> str:
    """`$schema` 메타 키를 뗀다 — 클로드 CLI 는 그대로 넘기면 모델을 부르기 전에 거절한다."""
    data = json.loads(schema.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data.pop("$schema", None)
    return json.dumps(data, ensure_ascii=False)


def parse_json_output(stdout: str) -> dict:
    data = json_object_in_text(stdout)
    if data is None:
        raise RuntimeError(f"CLI did not return JSON output\nstdout: {stdout[-2000:]}")
    return data


def json_object_in_text(value: object) -> dict | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char == "{":
            try:
                parsed, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def make_client(provider: str, cli: str, cwd: Path, add_dirs: tuple[str, ...], effort: str = "",
                allowed: tuple[str, ...] = (), denied: tuple[str, ...] = (), timeout: int = 2400,
                task_dir: Path | None = None):
    if provider == "claude":
        return ClaudeClient(cli=cli, cwd=cwd, timeout_seconds=timeout, allowed_tools=allowed, disallowed_tools=denied,
                            add_dirs=add_dirs, effort=effort)
    if provider == "codex":
        return CodexClient(cli=cli, cwd=cwd, timeout_seconds=timeout, add_dirs=add_dirs, effort=effort)
    if provider == "gemini":
        return GeminiClient(cli=cli, cwd=cwd, timeout_seconds=timeout, add_dirs=add_dirs)
    if provider in ("copilot", "cursor"):
        if task_dir is None:
            raise ValueError(f"{provider} 는 지시문 파일 폴더(task_dir)가 필요하다")
        if provider == "copilot":
            return CopilotClient(cli=cli, cwd=cwd, task_dir=task_dir, timeout_seconds=timeout, add_dirs=add_dirs)
        return CursorClient(cli=cli, cwd=cwd, task_dir=task_dir, timeout_seconds=timeout)
    raise ValueError(f"모르는 AI: {provider}")


# ── 모델 목록 ───────────────────────────────────────────────────────────────

def _account_home(ai: str, default: Path) -> Path:
    """지금 계정 폴더(accounts.py). 기본 계정이거나 그 폴더에 아직 목록이 없으면(막 로그인함) 기본 자리."""
    from memodesk import accounts   # 늦게 — accounts 가 config 를 읽는다
    home = accounts.folder(ai)
    return home if home and any(home.iterdir()) else default


def claude_models() -> list[dict]:
    """Claude Code 가 받아 둔 모델 목록(~/.claude/cache/model-catalog/*-cc.json). 못 읽으면 CLI 가 받는 별칭 몇 개."""
    folder = _account_home("claude", Path.home() / ".claude") / "cache" / "model-catalog"
    paths = sorted(folder.glob("*-cc.json"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    for path in paths:
        try:
            models = json.loads(path.read_text(encoding="utf-8"))["catalog"]["config"]["models"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        out = []
        for m in models:
            options = (m.get("thinking") or {}).get("effort_options") or []
            out.append({"id": m["id"], "name": m.get("name") or m["id"], "main": m.get("section") == "main",
                        "efforts": [o["id"] for o in options],
                        "recommended": next((o["id"] for o in options
                                             if (o.get("badge") or {}).get("message") == "Recommended"), "")})
        if out:
            return out
    return [{"id": a, "name": n, "main": True, "efforts": ["low", "medium", "high", "xhigh", "max"], "recommended": ""}
            for a, n in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku"))]


def codex_models() -> list[dict]:
    """Codex CLI 가 받아 둔 모델 목록(~/.codex/models_cache.json, 보이는 것만, 추천 순)."""
    try:
        models = json.loads((_account_home("codex", Path.home() / ".codex") / "models_cache.json").read_text(encoding="utf-8")).get("models", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    out = []
    for m in sorted((m for m in models if isinstance(m, dict) and m.get("visibility") == "list"), key=lambda m: m.get("priority", 99)):
        if m.get("slug"):
            out.append({"id": m["slug"], "name": m.get("display_name") or m["slug"], "main": True,
                        "efforts": [lv.get("effort") for lv in m.get("supported_reasoning_levels") or [] if lv.get("effort")],
                        "recommended": m.get("default_reasoning_level") or ""})
    return out


def model_list(provider: str) -> list[dict]:
    return {"claude": claude_models, "codex": codex_models}.get(provider, lambda: [])()
