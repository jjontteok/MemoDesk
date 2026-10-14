"""MemoDesk 핵심 — 메모 · 프로젝트 · 백업/되돌림 · 묶음 고르기 · 실패 이유 · API.

    python -B -m unittest discover -s tests

기록 폴더는 시험마다 임시 폴더로 바꾼다(MEMODESK_DATA). AI 는 부르지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ["MEMODESK_DATA"] = _TMP.name
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memodesk import config, failures, notes, projects, providers, runner, server, setup  # noqa: E402


def reset_data() -> None:
    for path in sorted(Path(_TMP.name).rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()


class NotesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(dir=_TMP.name))

    def test_add_order_move_and_ids_never_reused(self) -> None:
        a = notes.add(self.dir, "첫째")
        b = notes.add(self.dir, "둘째")
        c = notes.add(self.dir, "셋째", before=a["id"])
        self.assertEqual([n["id"] for n in notes.load(self.dir)], [c["id"], a["id"], b["id"]])
        self.assertEqual(a["id"], "M01")
        notes.move(self.dir, c["id"], None)
        self.assertEqual([n["id"] for n in notes.load(self.dir)][-1], c["id"])
        notes.remove(self.dir, b["id"])
        self.assertEqual(notes.add(self.dir, "넷째")["id"], "M04")   # 지운 번호를 다시 쓰지 않는다

    def test_human_note_never_queued(self) -> None:
        h = notes.add(self.dir, "사람이 할 일", "human")
        self.assertEqual(h["status"], "open")
        with self.assertRaises(ValueError):
            notes.set_status(self.dir, [h["id"]], "queued")
        self.assertEqual(notes.runnable_groups(notes.load(self.dir)), [])
        notes.set_kind(self.dir, h["id"], "code")
        self.assertEqual(notes.load(self.dir)[0]["status"], "queued")

    def test_groups_take_consecutive_same_kind_and_respect_busy_lane(self) -> None:
        a = notes.add(self.dir, "a")
        b = notes.add(self.dir, "b")
        notes.add(self.dir, "사람", "human")
        groups = notes.runnable_groups(notes.load(self.dir))
        self.assertEqual([(lane, [n["id"] for n in g]) for lane, g in groups], [("ai", [a["id"], b["id"]])])
        self.assertEqual(notes.runnable_groups(notes.load(self.dir), {"ai"}), [])

    def test_groups_split_by_ai(self) -> None:
        a = notes.add(self.dir, "a", ai="claude")
        b = notes.add(self.dir, "b", ai="claude")
        notes.add(self.dir, "c", ai="codex")
        groups = notes.runnable_groups(notes.load(self.dir))
        self.assertEqual([[n["id"] for n in g] for _, g in groups], [[a["id"], b["id"]]])   # 다른 AI 에서 끊고, 한 줄로 차례대로
        notes.set_ai(self.dir, b["id"], "codex")
        self.assertEqual([[n["id"] for n in g] for _, g in notes.runnable_groups(notes.load(self.dir))], [[a["id"]]])

    def test_requeue_stamps_requeued_at(self) -> None:
        """다시 맡기면 requeued_at — 처리된 메모 목록에서 맨 위로(2026-10-14). 멈춤으로 대기로 돌아가는 것은 아니다."""
        note = notes.add(self.dir, "버튼 크게")
        notes.set_status(self.dir, [note["id"]], "working")
        notes.set_status(self.dir, [note["id"]], "queued", "멈춤")
        self.assertNotIn("requeued_at", notes.load(self.dir)[0])
        notes.set_status(self.dir, [note["id"]], "review")
        notes.refine(self.dir, note["id"], "조금 더")
        self.assertIn("requeued_at", notes.load(self.dir)[0])

    def test_refine_keeps_previous_result_for_prompt(self) -> None:
        a = notes.add(self.dir, "버튼 글자 바꾸기")
        notes.set_result(self.dir, a["id"], "review", {"label": "고침", "headline": "바꿨어요", "detail": "- 글자", "files": ["a.html"]})
        notes.refine(self.dir, a["id"], "조금 더 크게")
        note = notes.load(self.dir)[0]
        self.assertEqual(note["status"], "queued")
        self.assertNotIn("result", note)
        block = notes.prompt_block(note, self.dir)
        self.assertIn("지난번 결과: 고침 — 바꿨어요", block)
        self.assertIn("조금 더 크게", block)
        self.assertIn("a.html", block)


class ProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_data()
        self.work = Path(tempfile.mkdtemp())

    def test_add_edit_overlap_and_refusals(self) -> None:
        project, warning = projects.add("My Site", str(self.work))
        self.assertEqual((project["id"], warning), ("my-site", ""))
        with self.assertRaises(ValueError):
            projects.add("again", str(self.work))                       # 같은 경로
        inner = self.work / "sub"
        inner.mkdir()
        _, warning = projects.add("inner", str(inner))
        self.assertIn("안에 있습니다", warning)                          # 겹치면 막지 않고 경고
        with self.assertRaises(ValueError):
            projects.add("self", str(config.APP_DIR))                    # MemoDesk 자신
        with self.assertRaises(ValueError):
            projects.add("relative", "some/folder")                      # 상대 경로
        edited, _ = projects.edit("my-site", {"name": "새 이름", "group": "팀A", "excludes": "big\nvideos"})
        self.assertEqual((edited["id"], edited["name"], edited["excludes"]), ("my-site", "새 이름", ["big", "videos"]))

    def test_korean_name_gets_ascii_id_and_removed_folder_is_not_reused(self) -> None:
        project, _ = projects.add("홈페이지", str(self.work))
        self.assertTrue(projects.ID_RE.match(project["id"]))
        notes.add(projects.data_dir(project["id"]), "옛 메모")
        projects.remove(project["id"], keep_records=True)
        again, _ = projects.add("홈페이지", str(self.work))
        self.assertNotEqual(again["id"], project["id"])                  # 남겨 둔 기록을 물려받지 않는다
        self.assertEqual(notes.load(projects.data_dir(again["id"])), [])


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_data()
        self.work = Path(tempfile.mkdtemp())
        (self.work / "src").mkdir()
        (self.work / "src" / "a.txt").write_text("원래", encoding="utf-8")
        (self.work / "keep.txt").write_text("그대로", encoding="utf-8")
        (self.work / "node_modules" / "x").mkdir(parents=True)
        (self.work / "node_modules" / "x" / "big.js").write_text("// 큰 의존성", encoding="utf-8")
        self.project, _ = projects.add("work", str(self.work))

    def test_restore_only_this_jobs_changes_and_shelve_new_files(self) -> None:
        pid = self.project["id"]
        runner.backup_project(pid, "20260101-000000", "code")
        marker = runner.active_marker(pid, "ai")
        self.assertNotIn("node_modules/x/big.js", json.loads(marker.read_text(encoding="utf-8"))["files"])
        (self.work / "src" / "a.txt").write_text("AI 가 바꿈", encoding="utf-8")
        (self.work / "new.txt").write_text("새 파일", encoding="utf-8")
        (self.work / "node_modules" / "x" / "added.js").write_text("설치됨", encoding="utf-8")
        (self.work / "keep.txt").unlink()
        restored = runner.restore_project(pid, marker)
        self.assertEqual((self.work / "src" / "a.txt").read_text(encoding="utf-8"), "원래")
        self.assertTrue((self.work / "keep.txt").exists())
        self.assertFalse((self.work / "new.txt").exists())
        self.assertTrue((projects.data_dir(pid) / "orphans" / "20260101-000000" / "new.txt").exists())   # 지우지 않고 옮김
        self.assertTrue((self.work / "node_modules" / "x" / "added.js").exists())   # 제외 폴더는 건드리지 않는다
        self.assertFalse(marker.exists())
        self.assertTrue(any("new.txt" in r for r in restored))

    def test_size_cap_refuses_without_writing(self) -> None:
        old = runner.BACKUP_MAX_BYTES
        runner.BACKUP_MAX_BYTES = 3
        try:
            with self.assertRaises(ValueError):
                runner.backup_project(self.project["id"], "20260101-000001", "code")
        finally:
            runner.BACKUP_MAX_BYTES = old
        self.assertFalse(runner.active_marker(self.project["id"], "ai").exists())

    def test_path_rule_excludes_only_that_subtree(self) -> None:
        files = runner.project_files(self.work, ["src"])
        self.assertNotIn("src/a.txt", files)
        self.assertEqual(runner.project_files(self.work, ["src/a.txt"]), ["keep.txt", "node_modules/x/big.js"])


class FailureTests(unittest.TestCase):
    def test_reasons_and_echoed_text_ignored(self) -> None:
        self.assertIn("로그인", failures.reason("Invalid API key · Please run /login"))
        self.assertIn("한도", failures.reason('{"type":"result","is_error":true,"result":"usage limit reached"}'))
        echoed = json.dumps({"type": "assistant", "message": "문서 예시: Invalid API key"})
        self.assertEqual(failures.reason(echoed), "")                    # AI 가 읽은 글 속 문구는 오류가 아니다
        self.assertEqual(failures.reason("KeyError: 'x'"), "")


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_data()

    def test_must_add_ai_first(self) -> None:
        data = setup.check(force=True)
        self.assertEqual([i["id"] for i in data["items"]], ["python", "ai"])
        self.assertEqual(data["groups"], [])
        self.assertFalse(data["ready"])
        self.assertEqual([c["id"] for c in data["providers"]], ["claude", "codex", "copilot", "cursor", "gemini"])
        with self.assertRaises(ValueError):
            setup.run_action("install_cli")                                     # 추가한 AI 가 없으면 설치할 것도 없다

    def test_several_ais_each_with_own_steps(self) -> None:
        setup.run_action("add", "claude")
        setup.run_action("add", "cursor")
        setup.run_action("add", "gemini")
        data = setup.check(force=True)
        self.assertEqual(setup.added(), ["claude", "cursor", "gemini"])
        self.assertEqual([i["id"] for i in data["items"]], ["python", "ai", "git"])   # Git 은 Claude 를 추가했을 때만
        steps = {g["ai"]: [s["id"] for s in g["steps"]] for g in data["groups"]}
        self.assertEqual(steps["claude"], ["claude:cli", "claude:login"])
        self.assertEqual(steps["cursor"], ["cursor:cli", "cursor:login"])
        self.assertEqual(steps["gemini"], ["gemini:node", "gemini:cli", "gemini:login"])   # Gemini 는 Node.js 먼저
        self.assertEqual(data["ready"], any(g["ready"] for g in data["groups"]))           # 하나라도 준비되면 쓸 수 있다
        setup.run_action("remove", "cursor")
        self.assertEqual(setup.added(), ["claude", "gemini"])
        with self.assertRaises(ValueError):
            setup.run_action("add", "nope")

    def test_old_single_choice_is_read_as_added(self) -> None:
        config.update(ai="codex")
        self.assertEqual(setup.added(), ["codex"])

    def test_unknown_action_refused(self) -> None:
        setup.run_action("add", "claude")
        with self.assertRaises(ValueError):
            setup.run_action("rm -rf /")                                         # 고정된 동작만 받는다

    def test_job_uses_memo_ai_and_refuses_missing_program(self) -> None:
        project, _ = projects.add("noai", tempfile.mkdtemp())
        folder = projects.data_dir(project["id"])
        note = notes.add(folder, "할 일")
        with self.assertRaises(ValueError):
            runner.ai_job(project["id"], [note])                                 # AI 를 하나도 안 추가했다
        note = notes.add(folder, "할 일", ai="cursor")
        old = providers.find_cli
        providers.find_cli = lambda pid: None
        try:
            with self.assertRaises(ValueError) as caught:
                runner.ai_job(project["id"], [note])                             # 메모의 AI(Cursor)가 설치 안 됨
            self.assertIn("Cursor", str(caught.exception))
        finally:
            providers.find_cli = old
        self.assertTrue(all(n["status"] == "queued" for n in notes.load(folder)))   # 아무것도 안 바꿨다
        self.assertFalse(runner.active_marker(project["id"], "ai").exists())

    def test_copilot_and_cursor_get_task_file_not_long_argument(self) -> None:
        """Copilot · Cursor 는 지시문을 파일로 받는다 — Windows 의 .cmd 실행 파일은 여러 줄 · 특수 문자 인자가 깨진다."""
        from memodesk import ai_clients
        captured = {}
        answer = json.dumps({"notes": [], "summary": "ok"})

        def fake_call(command, prompt, cwd, timeout, name):
            captured["cmd"] = command

            class Result:
                stdout = json.dumps({"type": "result", "is_error": False, "result": answer}) if name.startswith("Cursor") else answer
            return Result()

        old = ai_clients._call
        ai_clients._call = fake_call
        try:
            tmp = Path(tempfile.mkdtemp())
            schema = config.APP_DIR / "schemas" / "fix_output.schema.json"
            prompt = "여러 줄\n지시문 % ^ & |"
            for pid in ("copilot", "cursor"):
                client = ai_clients.make_client(pid, pid, tmp, (), task_dir=tmp / "tasks")
                client.run_prompt(prompt, schema, tmp / f"{pid}.json")
                cmd = captured["cmd"]
                self.assertNotIn("\n", cmd[cmd.index("-p") + 1])                  # 명령줄에는 한 줄짜리 안내만
                task = next((tmp / "tasks").glob("task-*.md"))
                self.assertIn(prompt, task.read_text(encoding="utf-8"))          # 지시문 전체는 파일에
                self.assertEqual(json.loads((tmp / f"{pid}.json").read_text(encoding="utf-8"))["summary"], "ok")
                if pid == "copilot":
                    self.assertEqual(cmd[cmd.index("--deny-tool") + 1], "shell")   # 셸 명령(지우기 · git) 거부
                task.unlink()
        finally:
            ai_clients._call = old



class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_data()
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()

    def call(self, path: str, body: dict | None = None, header: bool = True) -> tuple[int, dict]:
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **({"X-Desk": "1"} if header else {})})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 시스템 프록시를 타지 않게
        try:
            with opener.open(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_add_project_note_and_paused_queue(self) -> None:
        work = tempfile.mkdtemp()
        code, data = self.call("/api/projects/add", {"name": "api", "path": work})
        self.assertEqual(code, 200)
        pid = data["project"]["id"]
        runner.set_paused(pid, True)                                     # AI 를 부르지 않게 멈춘 채로
        self.assertEqual(self.call("/api/notes", {"project": pid, "text": "할 일"})[0], 400)   # 보낼 AI 가 없으면 거절
        setup.add("claude")
        self.assertEqual(self.call("/api/notes", {"project": pid, "text": "할 일", "ai": "codex"})[0], 400)   # 추가 안 한 AI
        self.assertEqual(self.call("/api/notes", {"project": pid, "text": "할 일", "ai": "claude"})[0], 200)
        code, state = self.call("/api/state")
        row = next(p for p in state["projects"] if p["id"] == pid)
        self.assertEqual((row["paused"], [n["status"] for n in row["notes"]]), (True, ["queued"]))
        self.assertEqual(self.call("/api/notes", {"project": pid, "text": "x"}, header=False)[0], 403)   # CSRF 막기
        self.assertEqual(self.call("/api/notes", {"project": "nope", "text": "x"})[0], 400)
        self.assertEqual(self.call("/api/notes/status", {"project": pid, "id": "M01", "status": "working"})[0], 400)

    def test_delete_project_keeps_folder_and_moves_records_to_trash(self) -> None:
        work = Path(tempfile.mkdtemp())
        (work / "keep.txt").write_text("그대로", encoding="utf-8")
        pid = self.call("/api/projects/add", {"name": "delete-me", "path": str(work)})[1]["project"]["id"]
        runner.set_paused(pid, True)
        setup.add("claude")
        self.call("/api/notes", {"project": pid, "text": "할 일", "ai": "claude"})
        code, data = self.call("/api/projects/remove", {"project": pid, "delete_records": True})
        self.assertEqual(code, 200)
        self.assertTrue((work / "keep.txt").exists())                        # 실제 폴더는 그대로
        self.assertTrue(Path(data["moved_records"], "notes.json").exists())   # 기록은 휴지통으로
        self.assertNotIn(pid, [p["id"] for p in self.call("/api/state")[1]["projects"]])


if __name__ == "__main__":
    unittest.main()
