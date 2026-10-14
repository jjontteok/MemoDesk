"""메모 → 고른 AI(Claude · Codex · Gemini). 처리기(runner)가 작업으로 부른다 — 이 스크립트는 **결과만** 내고 메모 상태는 처리기가 바꾼다.

    python -B -m memodesk.agents.fix --project <id> --stamp <작업 번호> --provider claude|codex|gemini --cli <실행 파일> [--model …] [--effort …]

- AI 는 프로젝트 경로에서 돈다(그 폴더의 CLAUDE.md · AGENTS.md 를 스스로 읽는다).
- 열어 주는 다른 폴더는 메모 첨부 그림 폴더와 REMOVED_DIR 뿐 — 기록 폴더(notes.json)는 열지 않는다.
- AI 마다 안전장치가 다르다(ai_clients.py). Claude 는 `rm` · `git` 을 거부 목록으로 막는다 — `acceptEdits` 는 작업 폴더 안의
  `rm` 을 허용 목록과 상관없이 자동 허락한다(차시 작업대 실측). Codex 는 폴더 밖 쓰기를 막는 보호 모드, Gemini 는 파일 고치기만 자동 승인.
- 끝난 뒤 프로젝트가 git 레포 안에 있으면 **프로젝트 경로 밖**이 바뀌었는지 본다. 되돌리지는 않고 ⚠ 로 적는다.
- 결과는 `{기록 폴더}/last-fix.json`.

종료 코드: 0 끝남 · 1 실패
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from memodesk import config, notes, projects, providers, usage
from memodesk.ai_clients import make_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROMPT = config.APP_DIR / "prompts" / "fix_system.md"
SCHEMA = config.APP_DIR / "schemas" / "fix_output.schema.json"
RESULT_NAME = "last-fix.json"
ALLOWED_TOOLS = ("Bash(mv:*)", "Bash(mkdir:*)", "Bash(cp:*)")
DENIED_TOOLS = ("Bash(rm:*)", "Bash(rmdir:*)", "Bash(del:*)", "Bash(git:*)")


def git_root(path: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(out.stdout.strip()).resolve() if out.returncode == 0 and out.stdout.strip() else None


def git_changes(root: Path) -> set[str] | None:
    """레포의 바뀐 파일(레포 기준 경로). git 이 없거나 실패하면 None."""
    try:
        out = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-uall"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {line[3:].strip().strip('"') for line in out.stdout.splitlines()} if out.returncode == 0 else None


def build_prompt(project: dict, working: list[dict], folder: Path, removed_dir: Path) -> str:
    body = "\n\n".join(notes.prompt_block(n, folder) for n in working)
    parts = [PROMPT.read_text(encoding="utf-8").strip(),
             f"PROJECT: {project['name']}\nPROJECT_DIR: {project['path']}\nREMOVED_DIR: {removed_dir}"]
    if project.get("instructions"):
        parts.append(f"PROJECT_INSTRUCTIONS:\n{project['instructions']}")
    parts.append(f"## NOTES — 이번에 할 메모 {len(working)}건\n\n{body}")
    return "\n\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="MemoDesk 메모 → AI")
    parser.add_argument("--project", required=True)
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max", "ultra"])
    parser.add_argument("--provider", default="claude", choices=list(providers.PROVIDERS))
    parser.add_argument("--cli", default="", help="AI CLI 실행 파일(처리기가 찾은 경로). 없으면 PATH 에서")
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    args = parser.parse_args()

    project = projects.get(args.project)
    folder = projects.data_dir(args.project)
    path = Path(project["path"])
    working = [n for n in notes.load(folder) if n.get("status") == "working" and notes.kind_of(n) == "code"]
    if not working:
        print("맡을 코드 메모가 없다")
        return 1

    usage.bind(folder, tag=args.stamp)
    removed_dir = folder / "removed" / args.stamp
    removed_dir.mkdir(parents=True, exist_ok=True)
    attach_dir = folder / notes.ATTACH_DIR
    attach_dir.mkdir(parents=True, exist_ok=True)
    client = make_client(args.provider, args.cli or providers.get(args.provider)["cli"], path,
                         (str(attach_dir), str(removed_dir)), effort=args.effort or "",
                         allowed=ALLOWED_TOOLS, denied=DENIED_TOOLS, timeout=args.timeout_seconds)
    output = folder / RESULT_NAME
    output.unlink(missing_ok=True)
    print(f"메모 {len(working)}건 · {providers.get(args.provider)['name']} · {project['name']} · {path}")

    root = git_root(path)
    before = git_changes(root) if root else None
    client.run_prompt(build_prompt(project, working, folder, removed_dir), SCHEMA, output, model=args.model or None,
                      stage=f"fix:{args.provider}")
    if not output.exists():
        print("결과 파일이 없다")
        return 1
    result = json.loads(output.read_text(encoding="utf-8"))

    after = git_changes(root) if root else None
    if before is not None and after is not None:
        try:
            inside = path.resolve().relative_to(root).as_posix()
        except ValueError:
            inside = None
        prefix = "" if inside in (None, ".", "") else inside + "/"
        outside = sorted(p for p in after - before if inside is None or (prefix and not p.startswith(prefix)))
        if outside:
            warn = f"- ⚠ 프로젝트 경로 밖 파일이 바뀌었다(이 작업 또는 그사이 다른 손): {', '.join(outside[:10])}"
            print(warn)
            for item in result.get("notes", []):
                item["detail"] = "\n".join([str(item.get("detail", "")).rstrip(), warn]).strip()
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in result.get("notes", []):
        print(f"  {item.get('id')}: {item.get('result')} — {item.get('headline')}")
    print(f"요약: {result.get('summary')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
