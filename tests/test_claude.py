import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crew.adapters import claude
from crew.adapters.claude import SETTLE_GRACE, ClaudeAdapter

T0 = time.time()  # discovery compares real file mtimes with the poll clock
SID = "11111111-1111-4111-8111-111111111111"


class Home:
    """A synthetic ~/.claude shaped like the records the probes observed."""

    def __init__(self, root: Path, entrypoint="cli"):
        self.root, self.entrypoint, self.clock, self.n = root, entrypoint, T0, 0
        self.cwd = "/work/crew"
        (root / "projects/-work-crew").mkdir(parents=True)

    def path(self, sid=SID, agent=None):
        base = self.root / "projects/-work-crew"
        return base / sid / "subagents" / f"agent-{agent}.jsonl" if agent else base / f"{sid}.jsonl"

    def write(self, record, sid=SID, agent=None, dt=1.0):
        self.clock += dt
        self.n += 1
        stamp = datetime.fromtimestamp(self.clock, UTC).isoformat().replace("+00:00", "Z")
        record = {"uuid": f"u{self.n}", "timestamp": stamp, "sessionId": sid, "cwd": self.cwd,
                  "entrypoint": self.entrypoint, **record}
        path = self.path(sid, agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        return record["uuid"]

    def prompt(self, text="Fix the bug", **kw):
        return self.write({"type": "user", "message": {"role": "user", "content": text}}, **kw)

    def meta(self, text, **kw):
        return self.write({"type": "user", "isMeta": True, "message": {"content": text}}, **kw)

    def say(self, text, stop="end_turn", mid="m", **kw):
        message = {"id": f"{mid}{self.n}", "stop_reason": stop,
                   "content": [{"type": "text", "text": text}]}
        return self.write({"type": "assistant", "message": message}, **kw)

    def tool(self, name, args, tid="t1", **kw):
        block = {"type": "tool_use", "id": tid, "name": name, "input": args}
        message = {"id": f"m{self.n}", "stop_reason": "tool_use", "content": [block]}
        return self.write({"type": "assistant", "message": message}, **kw)

    def tool_result(self, tid="t1", **kw):
        block = {"type": "tool_result", "tool_use_id": tid, "content": "ok"}
        return self.write({"type": "user", "message": {"content": [block]}}, **kw)

    def system(self, subtype, **extra):
        return self.write({"type": "system", "subtype": subtype, **extra})

    def registry(self, status="idle", sid=SID, pid=None, **extra):
        directory = self.root / "sessions"
        directory.mkdir(exist_ok=True)
        entry = {"pid": pid or os.getpid(), "sessionId": sid, "cwd": "/work/crew",
                 "status": status, "statusUpdatedAt": int(self.clock * 1000), **extra}
        (directory / "1.json").write_text(json.dumps(entry))

    def event(self, name, sid=SID, **extra):
        self.clock += 1.0  # a callback always lands after the record that caused it
        return {"ts_ns": int(self.clock * 1e9), "harness": "claude", "hook_event_name": name,
                "session_id": sid, "transcript_path": str(self.path(sid)), **extra}


@pytest.fixture(autouse=True)
def discover_every_poll(monkeypatch):
    monkeypatch.setattr(claude, "DISCOVER_EVERY", 0.0)


@pytest.fixture
def home(tmp_path):
    return Home(tmp_path)


def poll(adapter, home, events=(), dt=0.0):
    home.clock += dt
    result = adapter.poll(list(events), home.clock)
    return {s.session_id: s for s in result.sessions}, result.completions


def test_tui_request_lifecycle(home):
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    request = home.prompt()
    home.tool("Bash", {"command": "pytest -q", "description": "Running tests"})
    sessions, done = poll(adapter, home)
    assert (sessions[SID].state, sessions[SID].activity) == ("working", "Running tests")
    assert sessions[SID].cwd == "/work/crew" and not done

    home.tool_result()
    home.say("Fixed. Two tests still fail.")
    home.system("stop_hook_summary")
    sessions, done = poll(adapter, home, dt=3600)  # a stop alone never settles the TUI
    assert sessions[SID].state == "working" and not done

    home.system("turn_duration")
    home.registry("idle")
    sessions, done = poll(adapter, home)
    assert sessions[SID].state == "idle" and sessions[SID].activity is None
    [completion] = done
    assert completion.request_id == request
    assert completion.response == "Fixed. Two tests still fail."
    assert poll(adapter, home, dt=60)[1] == []

    home.prompt("And another thing")  # a further request in the same session
    home.registry("busy")
    assert poll(adapter, home)[0][SID].state == "working"


def continuation(home):
    request = home.prompt()
    home.say("FIRST")
    home.meta("Stop hook feedback:\nkeep going")
    home.system("stop_hook_summary", hookErrors=["keep going"])
    return request


def test_tui_stop_hook_continuation_yields_only_the_settled_response(home):
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    request = continuation(home)
    assert poll(adapter, home, dt=3600)[1] == []
    home.write({"type": "assistant", "message": {"id": "final", "stop_reason": "end_turn",
                "content": [{"type": "thinking", "thinking": "..."}]}})
    home.write({"type": "assistant", "message": {"id": "final", "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "SECOND"}]}})
    home.system("stop_hook_summary")
    home.system("turn_duration")
    [completion] = poll(adapter, home)[1]
    assert (completion.request_id, completion.response) == (request, "SECOND")


def test_hosted_settles_after_grace_but_never_on_a_continuing_stop(tmp_path):
    home = Home(tmp_path, entrypoint="sdk-cli")
    adapter = ClaudeAdapter(home.root)
    start = home.event("SessionStart")
    request = continuation(home)
    sessions, done = poll(adapter, home, [start], dt=3600)  # blocked stop, slow model
    assert sessions[SID].state == "working" and not done
    home.say("SECOND")
    home.system("stop_hook_summary")
    assert poll(adapter, home, dt=SETTLE_GRACE - 1)[1] == []
    sessions, done = poll(adapter, home, dt=2)
    assert [(c.request_id, c.response) for c in done] == [(request, "SECOND")]
    assert sessions[SID].state == "idle"
    assert done[0].completed_at == pytest.approx(home.clock - SETTLE_GRACE - 1, abs=0.01)


def test_a_response_with_no_settling_record_finishes_after_a_quiet_period(home):
    """Older TUIs write no `turn_duration`; sessions without stop hooks write no summary."""
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    request = home.prompt()
    home.say("DONE")
    assert poll(adapter, home, dt=SETTLE_GRACE + 1)[1] == []  # still busy: a stop hook may run
    home.registry("idle")
    [done] = poll(adapter, home)[1]
    assert (done.request_id, done.response) == (request, "DONE")

    # A slow stop hook can still send the model back to work after that: the
    # continuation settles under the same request and replaces the entry.
    home.meta("Stop hook feedback:\nkeep going")
    home.say("REALLY DONE")
    home.system("turn_duration")
    [later] = poll(adapter, home)[1]
    assert (later.request_id, later.response) == (request, "REALLY DONE")
    assert later.completed_at > done.completed_at


def test_hosted_settles_at_session_end_or_next_prompt(tmp_path):
    home = Home(tmp_path, entrypoint="sdk-cli")
    adapter = ClaudeAdapter(home.root)
    home.prompt()
    home.say("ONE")
    home.system("stop_hook_summary")
    home.prompt("next")
    sessions, done = poll(adapter, home, [home.event("SessionStart")])
    assert [c.response for c in done] == ["ONE"] and sessions[SID].state == "working"
    home.say("TWO")
    home.system("stop_hook_summary")
    sessions, done = poll(adapter, home, [home.event("SessionEnd")])
    assert [c.response for c in done] == ["TWO"] and SID not in sessions


@pytest.mark.parametrize("ending", ["interrupt", "api_error", "exit"])
def test_unfinished_requests_produce_no_completion(home, ending):
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    home.prompt()
    home.say("Partial thoughts", stop="tool_use")
    if ending == "interrupt":
        home.prompt([{"type": "text", "text": "[Request interrupted by user]"}])
        home.registry("idle")
    elif ending == "api_error":
        error = {"id": "err", "stop_reason": "end_turn",
                 "content": [{"type": "text", "text": "API Error"}]}
        home.write({"type": "assistant", "isApiErrorMessage": True, "message": error})
        home.system("turn_duration")
        home.registry("idle")
    else:
        (home.root / "sessions/1.json").unlink()  # the process is gone mid-request
    sessions, done = poll(adapter, home)
    assert done == []
    assert (SID in sessions) == (ending != "exit")
    if ending != "exit":
        assert sessions[SID].state == "idle"


def test_restart_and_replay_do_not_duplicate_completions(home):
    first = ClaudeAdapter(home.root)
    home.registry("busy")
    request = home.prompt()
    home.say("Half", stop="tool_use")
    poll(first, home)
    saved = json.loads(json.dumps(first.checkpoint()))  # survives a JSON round trip
    home.say("DONE")
    home.system("turn_duration")

    resumed = ClaudeAdapter(home.root, saved)
    assert [(c.request_id, c.response) for c in poll(resumed, home)[1]] == [(request, "DONE")]
    assert poll(ClaudeAdapter(home.root, resumed.checkpoint()), home)[1] == []
    # A collector that lost its checkpoint replays the same request identity.
    assert [c.request_id for c in poll(ClaudeAdapter(home.root), home)[1]] == [request]


def test_human_waits_come_from_actual_wait_evidence(home):
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    home.prompt()
    home.tool("Bash", {"command": "rm -rf build"})
    idle_prompt = home.event("Notification", notification_type="idle_prompt")
    assert poll(adapter, home, [idle_prompt])[0][SID].state == "working"  # readiness, not a wait

    asked = home.event("Notification", notification_type="permission_prompt")
    sessions, _ = poll(adapter, home, [asked], dt=6)
    assert (sessions[SID].state, sessions[SID].activity) == ("waiting", "Waiting for permission")
    assert poll(adapter, home, dt=3600)[0][SID].state == "waiting"

    home.registry("busy")  # approved: the registry changes before any transcript record
    assert poll(adapter, home, dt=1)[0][SID].state == "working"
    assert poll(adapter, home, dt=7200)[0][SID].state == "working"  # long tool stays working

    home.registry("waiting", waitingFor="dialog open")
    sessions, _ = poll(adapter, home)
    assert (sessions[SID].state, sessions[SID].activity) == ("waiting", "Waiting: dialog open")

    home.registry("busy")
    home.tool_result()
    home.tool("AskUserQuestion", {"questions": []}, tid="q1")
    assert poll(adapter, home)[0][SID].activity == "Waiting for an answer"
    home.tool_result("q1")
    assert poll(adapter, home)[0][SID].state == "working"


def test_hook_wait_closes_on_later_records_without_a_registry(tmp_path):
    home = Home(tmp_path, entrypoint="sdk-cli")
    adapter = ClaudeAdapter(home.root)
    home.prompt()
    home.tool("Bash", {"command": "make"})
    asked = home.event("Notification", notification_type="permission_prompt")
    events = [home.event("SessionStart"), asked]
    session = poll(adapter, home, events)[0][SID]
    assert session.state == "waiting" and session.gap
    home.tool_result()
    assert poll(adapter, home)[0][SID].state == "working"


def test_helpers_attach_to_their_evidenced_parent_only(home):
    adapter = ClaudeAdapter(home.root)
    other = "22222222-2222-4222-8222-222222222222"
    home.registry("busy")
    home.prompt()
    home.tool("Agent", {"description": "Read the code"})
    home.prompt("Read the code", agent="abc")
    home.tool("Read", {"file_path": "/work/crew/crew/model.py"}, agent="abc")
    home.path(agent="abc").with_suffix(".meta.json").write_text(
        json.dumps({"description": "Read the code", "agentType": "Explore"}))
    home.prompt("unrelated session in the same folder", sid=other)  # same cwd, no link

    sessions, _ = poll(adapter, home)
    helper = sessions[f"{SID}/abc"]
    assert (helper.parent_id, helper.state, helper.activity) == (SID, "working", "Reading model.py")
    assert helper.title == "Read the code"
    assert sessions[SID].parent_id is None and other not in sessions  # no liveness: not shown

    home.say("CHILD_DONE", agent="abc")
    stop = home.event("SubagentStop", agent_id="abc")
    assert poll(adapter, home, [stop])[0][f"{SID}/abc"].state == "idle"

    home.prompt("continue", agent="abc")  # SendMessage resumes the same native helper
    sessions, _ = poll(adapter, home, [home.event("SubagentStart", agent_id="abc")])
    assert sessions[f"{SID}/abc"].state == "working"
    assert [s for s in sessions if s.startswith(SID + "/")] == [f"{SID}/abc"]

    home.tool("SubagentHandback", {}, agent="abc")  # a final report needs no stop hook
    assert poll(adapter, home)[0][f"{SID}/abc"].state == "idle"

    home.prompt("another", agent="bg")  # still in a long tool when the author moves on
    home.tool("Bash", {"command": "sleep 600"}, agent="bg")
    home.say("Parent answered.")
    home.system("turn_duration")
    home.prompt("next request")
    sessions, _ = poll(adapter, home, dt=30)
    assert sessions[f"{SID}/bg"].state == "working"
    quiet = poll(adapter, home, dt=600)[0][f"{SID}/bg"]
    assert (quiet.state, quiet.gap) == ("unknown", "No recent helper evidence")

    home.prompt("go deeper", agent="nested")
    home.path(agent="nested").with_suffix(".meta.json").write_text(
        json.dumps({"agentType": "Explore", "parentAgentId": "abc"}))
    assert poll(adapter, home)[0][f"{SID}/nested"].parent_id == f"{SID}/abc"


def test_sessions_without_liveness_evidence_are_marked_not_guessed(tmp_path):
    home = Home(tmp_path, entrypoint="sdk-cli")
    adapter = ClaudeAdapter(home.root)
    home.prompt()
    home.tool("Bash", {"command": "sleep 600"})
    session = poll(adapter, home)[0][SID]
    assert session.state == "working" and "Liveness" in session.gap
    assert poll(adapter, home, dt=300)[0][SID].state == "unknown"
    assert poll(adapter, home, dt=7200)[0] == {}  # never promoted to idle


def test_live_session_before_its_first_prompt_is_idle(home):
    home.registry("idle", name="crew-03")
    session = poll(ClaudeAdapter(home.root), home)[0][SID]
    assert (session.state, session.title, session.cwd) == ("idle", "crew-03", "/work/crew")


def test_unreadable_transcript_is_reported_and_others_continue(home):
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    home.prompt()
    bad = home.root / "projects/-work-crew/33333333-3333-4333-8333-333333333333.jsonl"
    bad.mkdir()
    result = adapter.poll([], home.clock)
    assert [s.session_id for s in result.sessions] == [SID] and result.gaps


def test_unexpected_shapes_cost_one_record_not_the_adapter(home):
    adapter = ClaudeAdapter(home.root)
    home.registry("busy")
    home.prompt()
    home.write({"type": "assistant", "message": {"id": "odd", "content": "a bare string"}})
    home.write({"type": "assistant", "message": {"id": "odd2", "content": [1, None, "x"]}})
    home.write({"type": "user", "message": {"content": [{"type": "tool_result"}, 7]}})
    home.tool("Bash", {"command": "make", "description": "Building"})
    sessions = home.root / "sessions"
    (sessions / "2.json").write_text("[]")
    (sessions / "3.json").write_text(json.dumps({"pid": os.getpid(), "status": "busy"}))
    home.registry("busy", statusUpdatedAt=None)
    result = adapter.poll([], home.clock)
    assert [(s.session_id, s.state, s.activity) for s in result.sessions] == [
        (SID, "working", "Building")]
