"""AI CLI 호출 — 1차는 클로드(Claude Code CLI)만. 코덱스는 2차에 그림 · 검증 줄과 함께 더한다.

모든 호출이 여기를 지나므로 **걸린 시간과 토큰을 여기서 적는다**(`usage.record_call`). 실패해도 걸린 시간은 남긴다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from memodesk import usage

PROVIDER_CLAUDE = "claude"


def resolve_executable(name: str) -> str:
    """셸이 고르는 것과 같은 실행 파일을 고정한다. Windows 의 `CreateProcess` 는 PATH 를 셸과 다른 순서로 찾아
    같은 이름의 다른 설치본을 부를 수 있다(차시 작업대 실측 — 옛 standalone 코덱스가 돌아 새 모델을 거절했다)."""
    return shutil.which(name) or name


@dataclass(frozen=True)
class ClaudeClient:
    claude_bin: str
    cwd: Path                      # 작업 폴더 = 프로젝트 경로. 그 폴더의 CLAUDE.md 를 클로드가 스스로 읽는다
    timeout_seconds: int = 2400
    permission_mode: str = "acceptEdits"
    # 미리 허용할 명령. `acceptEdits` 는 작업 폴더 안의 `mkdir` · `mv` · `rm` 같은 파일 명령을 목록과 상관없이 자동 허락한다
    # (차시 작업대 실측 2026-10-01 — `rm c.txt` 가 돌았다). 막아야 하는 것은 disallowed_tools 에 적는다 — 거부가 허용보다 앞선다
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    # 사용자 전역 설정(~/.claude/settings.json)의 허용 규칙을 물려받지 않는다 — PC 마다 전역 설정이 달라도 같은 권한으로 돈다
    setting_sources: str = "project"
    add_dirs: tuple[str, ...] = ()   # 작업 폴더 밖에서 읽거나 쓸 폴더(첨부 그림 · 치운 파일 보관 폴더)
    effort: str = ""

    def run_prompt(self, prompt: str, output_schema: Path, output_path: Path, model: str | None = None,
                   stage: str | None = None) -> dict | None:
        started = time.monotonic()
        try:
            got = self._run_prompt(prompt, output_schema, output_path, model)
        except BaseException as exc:
            usage.record_call(stage, PROVIDER_CLAUDE, model, time.monotonic() - started, None, False, f"{type(exc).__name__}: {exc}")
            raise
        usage.record_call(stage, PROVIDER_CLAUDE, model or claude_model(got), time.monotonic() - started, got, True)
        return got

    def _run_prompt(self, prompt: str, output_schema: Path, output_path: Path, model: str | None) -> dict | None:
        command = self.build_command(output_schema, model)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(command, input=prompt, text=True, capture_output=True, encoding="utf-8",
                                       errors="replace", cwd=self.cwd, timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Claude Code CLI timed out in non-interactive mode (timeout_seconds: {self.timeout_seconds})") from exc
        if completed.returncode != 0:
            raise RuntimeError(f"Claude Code CLI failed\nstdout: {completed.stdout}\nstderr: {completed.stderr}")
        result = parse_json_output(completed.stdout)
        if result.get("is_error") is True:
            raise RuntimeError(f"Claude Code CLI returned an error result\nresult: {result.get('result')}\nstderr: {completed.stderr}")
        structured = result.get("structured_output")
        if not isinstance(structured, dict):
            structured = json_object_in_text(result.get("result"))
        if structured is None:
            raise RuntimeError(f"Claude Code CLI did not return structured output\nstdout: {completed.stdout}")
        output_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return extract_usage(result)

    def build_command(self, output_schema: Path, model: str | None = None) -> list[str]:
        command = [resolve_executable(self.claude_bin)]
        if model:
            command += ["--model", model]
        if self.effort:
            command += ["--effort", self.effort]
        command += ["-p", "Execute the complete task described in stdin and return only the requested structured output.",
                    "--output-format", "json", "--json-schema", schema_for_claude(output_schema),
                    "--permission-mode", self.permission_mode, "--setting-sources", self.setting_sources]
        if self.allowed_tools:
            command += ["--allowedTools", *self.allowed_tools]
        if self.disallowed_tools:
            command += ["--disallowedTools", *self.disallowed_tools]
        for folder in self.add_dirs:
            command += ["--add-dir", folder]
        return command


def schema_for_claude(output_schema: Path) -> str:
    """`$schema` 메타 키를 떼고 넘긴다 — 그대로 넘기면 CLI 가 모델을 부르기 전에 `no schema with key or ref` 로 거절한다."""
    schema = json.loads(output_schema.read_text(encoding="utf-8"))
    if isinstance(schema, dict):
        schema.pop("$schema", None)
    return json.dumps(schema, ensure_ascii=False)


def parse_json_output(stdout: str) -> dict:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude Code CLI did not return JSON output\nstdout: {stdout}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"Claude Code CLI returned non-object JSON output\nstdout: {stdout}")
    return result


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


def extract_usage(result: dict) -> dict | None:
    out: dict = {}
    if isinstance(result.get("usage"), dict):
        out["usage"] = result["usage"]
    if isinstance(result.get("modelUsage"), dict):
        out["model_usage"] = result["modelUsage"]
    if result.get("total_cost_usd") is not None:
        out["total_cost_usd"] = result["total_cost_usd"]
    return out or None


def claude_model(got: dict | None) -> str | None:
    """`--model` 없이 부르면 어느 모델이 돌았는지 `modelUsage` 키로만 알 수 있다."""
    models = (got or {}).get("model_usage") or {}
    return next(iter(models), None) if isinstance(models, dict) else None


def claude_models() -> list[dict]:
    """Claude Code 가 받아 둔 모델 목록(~/.claude/cache/model-catalog/*-cc.json) — 이름 · 추론 강도 · 추천값.
    지어내지 않는다. 못 읽으면 CLI 가 받는 별칭 몇 개로 대신한다."""
    folder = Path.home() / ".claude" / "cache" / "model-catalog"
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
