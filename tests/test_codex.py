import json
import os
import socket
import struct
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crew.adapters import codex
from crew.adapters.codex import OUTSIDE_DAEMON, CodexAdapter, Daemon

MAIN, CHILD = "0199aaaa-main", "0199bbbb-child"


class FakeDaemon:
    """Stands in for the daemon connection; records every method it is asked."""

    def __init__(self):
        self.threads: dict[str, dict] = {}
        self.down = False

    def __call__(self, _path):
        if self.down:
            raise ConnectionRefusedError("down")
        return self

    def loaded(self):
        if self.down:
            raise ConnectionError("closed")
        return self.threads

    def close(self):
        pass

    def status(self, thread_id, kind, *flags, **info):
        status = {"type": kind} | ({"activeFlags": list(flags)} if kind == "active" else {})
        self.threads[thread_id] = {"status": status, **info}


class Home:
    def __init__(self, root: Path):
        self.root, self.clock = root, time.time()
        (root / "sessions/2026/10/07").mkdir(parents=True)
        (root / "app-server-control").mkdir()
        (root / "app-server-control/app-server-control.sock").touch()

    def path(self, thread_id):
        return self.root / f"sessions/2026/10/07/rollout-2026-10-07T10-00-00-{thread_id}.jsonl"

    def write(self, thread_id, kind, payload):
        self.clock += 1.0
        stamp = datetime.fromtimestamp(self.clock, UTC).isoformat().replace("+00:00", "Z")
        with self.path(thread_id).open("a") as f:
            f.write(json.dumps({"timestamp": stamp, "type": kind, "payload": payload}) + "\n")

    def meta(self, thread_id, source="cli", cwd="/work/crew"):
        self.write(thread_id, "session_meta", {"id": thread_id, "cwd": cwd, "source": source})

    def event(self, thread_id, kind, **payload):
        self.write(thread_id, "event_msg", {"type": kind, **payload})

    def turn(self, thread_id, turn, message="DONE"):
        self.event(thread_id, "task_started", turn_id=turn)
        self.event(thread_id, "task_complete", turn_id=turn, completed_at=int(self.clock),
                   last_agent_message=message)

    def call(self, thread_id, name, args):
        self.write(thread_id, "response_item",
                   {"type": "function_call", "name": name, "arguments": json.dumps(args)})

    def hook(self, thread_id, name):
        self.clock += 1.0
        return {"ts_ns": int(self.clock * 1e9), "harness": "codex", "hook_event_name": name,
                "session_id": thread_id, "transcript_path": str(self.path(thread_id))}


@pytest.fixture(autouse=True)
def every_poll(monkeypatch):
    monkeypatch.setattr(codex, "DISCOVER_EVERY", 0.0)
    monkeypatch.setattr(codex, "RECONNECT_EVERY", 0.0)


@pytest.fixture
def home(tmp_path):
    return Home(tmp_path)


def poll(adapter, home, events=(), dt=0.0):
    home.clock += dt
    result = adapter.poll(list(events), home.clock)
    return {s.session_id: s for s in result.sessions}, result


def test_daemon_status_drives_state_and_rollout_settles_requests(home):
    daemon = FakeDaemon()
    adapter = CodexAdapter(home.root, connect=daemon)
    home.meta(MAIN)
    home.event(MAIN, "user_message", message="Fix the flaky test")
    home.event(MAIN, "task_started", turn_id="turn-1")
    home.call(MAIN, "exec_command", {"cmd": "pytest -q\necho done"})
    daemon.status(MAIN, "active")
    session = poll(adapter, home)[0][MAIN]
    assert (session.state, session.activity) == ("working", "Running pytest -q")
    assert (session.title, session.cwd) == ("Fix the flaky test", "/work/crew")

    daemon.status(MAIN, "active", "waitingOnApproval")
    session = poll(adapter, home)[0][MAIN]
    assert (session.state, session.activity) == ("waiting", "Waiting for approval")
    daemon.status(MAIN, "active", "waitingOnUserInput")
    assert poll(adapter, home)[0][MAIN].activity == "Waiting for an answer"
    daemon.status(MAIN, "active")
    assert poll(adapter, home, dt=7200)[0][MAIN].state == "working"  # long tool stays working

    completed = int(home.clock)
    home.event(MAIN, "task_complete", turn_id="turn-1", completed_at=completed,
               last_agent_message="Fixed it.")
    daemon.status(MAIN, "idle")
    sessions, result = poll(adapter, home)
    assert sessions[MAIN].state == "idle" and sessions[MAIN].activity is None
    [done] = result.completions
    assert (done.request_id, done.response) == ("turn-1", "Fixed it.")
    assert done.completed_at == float(completed)

    home.turn(MAIN, "turn-2", "Second answer")  # a resumed thread keeps its identity
    assert [c.request_id for c in poll(adapter, home)[1].completions] == ["turn-2"]
    assert poll(adapter, home)[1].completions == []


@pytest.mark.parametrize(
    ("name", "args", "expected"),
    [
        ("exec", 'await tools.exec_command({cmd:"/bin/sleep 6"});', "Running /bin/sleep 6"),
        ("exec", "const r = await tools.exec_command({\n  cmd: `pytest -q\nls`,\n});",
         "Running pytest -q"),
        ("exec", 'await tools.exec_command({cmd: "node <<EOF\\nimport x"})', "Running node <<EOF"),
        ("exec", 'await tools.apply_patch("*** Begin Patch");', "Editing files"),
        ("exec", "await tools.web__run({q: 1})", "Using web run"),
        ("exec", "1 + 1", "Running a script"),
        ("spawn_agent", {"message": "go"}, "Delegating to a helper"),
        ("wait_agent", {"timeout_ms": 1}, "Waiting on a helper"),
        ("some_tool", {}, "Using some_tool"),
    ],
)
def test_activity_descriptions(name, args, expected):
    assert codex.describe(name, args) == expected


def test_policy_callbacks_are_not_human_waits(home):
    daemon = FakeDaemon()
    adapter = CodexAdapter(home.root, connect=daemon)
    home.meta(MAIN)
    home.event(MAIN, "task_started", turn_id="turn-1")
    daemon.status(MAIN, "active")
    sessions, _ = poll(adapter, home, [home.hook(MAIN, "PermissionRequest")])
    assert sessions[MAIN].state == "working"


def test_aborted_or_empty_turns_do_not_finish(home):
    adapter = CodexAdapter(home.root, connect=FakeDaemon())
    home.meta(MAIN)
    home.event(MAIN, "task_started", turn_id="turn-1")
    home.event(MAIN, "turn_aborted", turn_id="turn-1", reason="interrupted")
    home.event(MAIN, "task_started", turn_id="turn-2")
    home.event(MAIN, "task_complete", turn_id="turn-2", last_agent_message=None)
    sessions, result = poll(adapter, home)
    assert result.completions == [] and sessions == {}


def test_helpers_need_an_evidenced_spawn_parent(home):
    daemon = FakeDaemon()
    adapter = CodexAdapter(home.root, connect=daemon)
    spawn = {"parent_thread_id": MAIN, "depth": 1, "agent_nickname": "Hopper", "agent_role": None}
    home.meta(MAIN)
    home.event(MAIN, "task_started", turn_id="turn-1")
    home.call(MAIN, "spawn_agent", {"task_name": "read the code", "message": "..."})
    home.meta(CHILD, {"subagent": {"thread_spawn": spawn}})
    home.event(CHILD, "task_started", turn_id="c-1")
    home.meta("review", {"subagent": {"other": "guardian"}})  # parent form not established
    home.event("review", "task_started", turn_id="r-1")
    home.meta("lookalike", "cli")  # same folder and nothing else in common
    daemon.status(MAIN, "active")
    daemon.status(CHILD, "active")
    daemon.status("review", "active", parentThreadId=MAIN)

    sessions, result = poll(adapter, home)
    assert set(sessions) == {MAIN, CHILD}
    assert (sessions[CHILD].parent_id, sessions[CHILD].title) == (MAIN, "Hopper")
    assert sessions[MAIN].activity == "Delegating: read the code"
    assert any("without an evidenced parent" in gap for gap in result.gaps)

    home.event(CHILD, "task_complete", turn_id="c-1", last_agent_message="CHILD_DONE")
    daemon.status(CHILD, "idle")
    sessions, result = poll(adapter, home)
    assert sessions[CHILD].state == "idle" and result.completions == []  # not the author's

    home.event(CHILD, "task_started", turn_id="c-2")  # the same native helper, resumed
    daemon.status(CHILD, "active")
    sessions, _ = poll(adapter, home)
    assert [s for s in sessions if s != MAIN] == [CHILD] and sessions[CHILD].state == "working"


def test_threads_outside_the_daemon_expose_their_gaps(home):
    adapter = CodexAdapter(home.root, connect=FakeDaemon())
    home.meta(MAIN)
    home.event(MAIN, "task_started", turn_id="turn-1")
    session = poll(adapter, home)[0][MAIN]
    assert session.state == "working" and "Liveness" in session.gap
    assert poll(adapter, home, dt=300)[0][MAIN].state == "unknown"

    session = poll(adapter, home, [home.hook(MAIN, "SessionStart")], dt=7200)[0][MAIN]
    assert (session.state, session.gap) == ("working", OUTSIDE_DAEMON)
    home.turn(MAIN, "turn-2")
    sessions, result = poll(adapter, home)
    assert sessions[MAIN].state == "idle" and len(result.completions) == 1
    assert MAIN not in poll(adapter, home, [home.hook(MAIN, "SessionEnd")])[0]


def test_daemon_outage_is_a_gap_and_records_still_settle(home):
    daemon = FakeDaemon()
    adapter = CodexAdapter(home.root, connect=daemon)
    home.meta(MAIN)
    daemon.status(MAIN, "idle")
    assert poll(adapter, home)[0][MAIN].state == "idle"

    daemon.down = True
    home.turn(MAIN, "turn-1")
    sessions, result = poll(adapter, home)
    assert MAIN not in sessions  # no status evidence: not guessed idle
    assert [c.request_id for c in result.completions] == ["turn-1"]
    assert any("unavailable" in gap for gap in result.gaps)

    daemon.down = False
    sessions, result = poll(adapter, home, dt=1)
    assert sessions[MAIN].state == "idle" and not result.gaps


def test_restart_and_replay_do_not_duplicate_completions(home):
    first = CodexAdapter(home.root, connect=FakeDaemon())
    home.meta(MAIN)
    home.event(MAIN, "task_started", turn_id="turn-1")
    poll(first, home)
    saved = json.loads(json.dumps(first.checkpoint()))
    home.event(MAIN, "task_complete", turn_id="turn-1", last_agent_message="DONE")
    resumed = CodexAdapter(home.root, saved, connect=FakeDaemon())
    assert [c.request_id for c in poll(resumed, home)[1].completions] == ["turn-1"]
    again = CodexAdapter(home.root, resumed.checkpoint(), connect=FakeDaemon())
    assert poll(again, home)[1].completions == []
    fresh = CodexAdapter(home.root, connect=FakeDaemon())
    assert [c.request_id for c in poll(fresh, home)[1].completions] == ["turn-1"]


def test_one_session_across_several_rollouts(home):
    daemon = FakeDaemon()
    adapter = CodexAdapter(home.root, connect=daemon)
    home.meta(MAIN)
    home.turn(MAIN, "turn-1", "MAIN ANSWER 1")
    # A forked helper's rollout repeats its parent's header after its own.
    spawn = {"parent_thread_id": MAIN, "depth": 1, "agent_nickname": "Curie"}
    home.meta(CHILD, {"subagent": {"thread_spawn": spawn}})
    home.write(CHILD, "session_meta", {"id": MAIN, "cwd": "/work/crew", "source": "cli"})
    home.turn(CHILD, "c-1", "CHILD REPORT")
    # A continued session reuses its id in a later rollout file.
    later = home.root / "sessions/2026/10/07/rollout-2026-10-07T11-00-00-continued.jsonl"
    home.path = lambda thread_id: later if thread_id == "continued" else Home.path(home, thread_id)
    home.write("continued", "session_meta", {"id": MAIN, "cwd": "/work/crew", "source": "cli"})
    home.turn("continued", "turn-2", "MAIN ANSWER 2")
    daemon.status(MAIN, "idle")
    daemon.status(CHILD, "idle")

    sessions, result = poll(adapter, home)
    assert [(c.session_id, c.response) for c in result.completions] == [
        (MAIN, "MAIN ANSWER 1"), (MAIN, "MAIN ANSWER 2")]
    assert (sessions[CHILD].parent_id, sessions[CHILD].title) == (MAIN, "Curie")
    assert sessions[MAIN].title != "Curie"


def frame(payload: bytes, opcode=1) -> bytes:
    head = bytes([0x80 | opcode])
    n = len(payload)
    return head + (bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n)) + payload


def test_daemon_client_only_reads(tmp_path):
    """The real WebSocket client against a scripted server on a Unix socket."""
    path = Path(f"/tmp/crew-test-{os.getpid()}.sock")  # AF_UNIX paths are length-limited
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    server.listen(1)
    methods, pongs = [], []

    def serve():
        conn, _ = server.accept()
        data = b""
        while b"\r\n\r\n" not in data:
            data += conn.recv(4096)
        conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")

        def read():
            head = conn.recv(2)
            opcode, n = head[0] & 15, head[1] & 127
            if n == 126:
                n = struct.unpack(">H", conn.recv(2))[0]
            mask, body = conn.recv(4), b""
            while len(body) < n:
                body += conn.recv(n - len(body))
            return opcode, bytes(b ^ mask[i % 4] for i, b in enumerate(body))

        while True:
            try:
                opcode, body = read()
            except (IndexError, OSError):
                return
            if opcode == 10:
                pongs.append(body)
                continue
            message = json.loads(body)
            methods.append(message["method"])
            if "id" not in message:
                continue
            reply = {"initialize": {}, "thread/loaded/list": {"data": ["bad", "t1"]},
                     "thread/read": {"thread": {"id": "t1", "status": {"type": "active",
                                     "activeFlags": ["waitingOnApproval"]}, "blob": "x" * 70000}}}
            conn.sendall(frame(b"hi", opcode=9))  # ping
            for pushed in ({"method": "thread/status/changed"}, {"id": 99, "method": "x/request"}):
                conn.sendall(frame(json.dumps(pushed).encode()))
            answer = {"id": message["id"], "result": reply[message["method"]]}
            if message.get("params", {}).get("threadId") == "bad":
                answer = {"id": message["id"], "error": {"code": -32600, "message": "unreadable"}}
            body = json.dumps(answer).encode()
            head = bytes([0x81, 127]) + struct.pack(">Q", len(body)) if len(body) > 65535 else b""
            conn.sendall(head + body if head else frame(body))

    threading.Thread(target=serve, daemon=True).start()
    try:
        daemon = Daemon(path)
        threads = daemon.loaded()
        daemon.close()
    finally:
        server.close()
        path.unlink()
    assert list(threads) == ["t1"]  # one unreadable thread does not blank the rest
    assert threads["t1"]["status"]["activeFlags"] == ["waitingOnApproval"]
    assert methods == ["initialize", "initialized", "thread/loaded/list", "thread/read",
                       "thread/read"]
    assert pongs and set(pongs) == {b"hi"}  # pings answered; server requests never are
