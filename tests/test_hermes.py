import importlib
import json
import os
import sqlite3
import sys
import time
import types

import pytest

from crew.adapters.hermes import NO_WAITS, HermesAdapter
from crew.journal import Journal

ALL_HOOKS = ["pre_llm_call", "post_llm_call", "on_session_end", "on_human_input_request",
             "on_human_input_resolved", "subagent_start", "subagent_stop"]


class Clock:
    def __init__(self):
        self.now = time.time()

    def event(self, name, **fields):
        self.now += 1.0
        return {"ts_ns": int(self.now * 1e9), "harness": "hermes", "event": name,
                "pid": os.getpid(), "platform": "cli", "cwd": "/work/crew", **fields}


@pytest.fixture
def clock():
    return Clock()


def poll(adapter, clock, *events):
    result = adapter.poll(list(events), clock.now)
    return {s.session_id: s for s in result.sessions}, result


def test_turn_lifecycle_with_paired_human_wait(tmp_path, clock):
    adapter = HermesAdapter(tmp_path)
    loaded = clock.event("plugin_loaded", hooks=ALL_HOOKS)
    sessions, result = poll(
        adapter, clock, loaded, clock.event("pre_llm_call", session_id="s", turn_id="t1"),
        clock.event("pre_tool_call", session_id="s", tool_name="terminal"),
    )
    assert (sessions["s"].state, sessions["s"].activity) == ("working", "Using terminal")
    assert sessions["s"].cwd == "/work/crew" and not result.gaps

    asked = clock.event("on_human_input_request", session_id="s", request_id="r1", kind="clarify")
    assert poll(adapter, clock, asked)[0]["s"].activity == "Waiting for an answer"
    answered = clock.event("on_human_input_resolved", session_id="s", request_id="r1",
                           outcome="submitted")
    assert poll(adapter, clock, answered)[0]["s"].state == "working"

    sessions, result = poll(
        adapter, clock,
        clock.event("post_llm_call", session_id="s", turn_id="t1", response="Blue"),
        clock.event("on_session_end", session_id="s", turn_id="t1", completed=True,
                    failed=False, interrupted=False),
    )
    assert sessions["s"].state == "idle"
    assert [(c.request_id, c.response) for c in result.completions] == [("t1", "Blue")]

    resumed = clock.event("pre_llm_call", session_id="s", turn_id="t2")  # same session, new turn
    assert poll(adapter, clock, resumed)[0]["s"].request_id == "t2"


@pytest.mark.parametrize("flags", [{"completed": False, "interrupted": True},
                                   {"completed": True, "failed": True},
                                   {"completed": False}])
def test_unfinished_turns_do_not_complete(tmp_path, clock, flags):
    adapter = HermesAdapter(tmp_path)
    _, result = poll(
        adapter, clock,
        clock.event("pre_llm_call", session_id="s", turn_id="t1"),
        clock.event("post_llm_call", session_id="s", turn_id="t1", response="partial"),
        clock.event("on_session_end", session_id="s", turn_id="t1", **flags),
    )
    assert result.completions == []


def test_missing_wait_observers_are_reported_not_inferred(tmp_path, clock):
    adapter = HermesAdapter(tmp_path)
    sessions, result = poll(
        adapter, clock, clock.event("plugin_loaded", hooks=["pre_llm_call"]),
        clock.event("pre_llm_call", session_id="s", turn_id="t1"),
        clock.event("pre_tool_call", session_id="s", tool_name="clarify"),
    )
    assert sessions["s"].state == "working" and result.gaps == [NO_WAITS]


def test_delegation_links_helpers_and_plain_parent_links_do_not(tmp_path, clock):
    table = ("CREATE TABLE sessions (id TEXT, cwd TEXT, git_repo_root TEXT, title TEXT,"
             " parent_session_id TEXT, model_config TEXT)")
    db = sqlite3.connect(tmp_path / "state.db")
    db.execute(table)
    db.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", [
        ("p", "/work/crew", None, "Main chat", None, None),
        ("branch", "/work/crew", None, "Branched", "p", "{}"),
        ("backfilled", None, None, None, "p", json.dumps({"_delegate_from": "p"})),
    ])
    db.commit()
    (tmp_path / "profiles/factory").mkdir(parents=True)  # one gateway serves every profile
    profile = sqlite3.connect(tmp_path / "profiles/factory/state.db")
    profile.execute(table)
    profile.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                    ("f", "/work/grove", None, "Factory run", None, None))
    profile.commit()
    adapter = HermesAdapter(tmp_path)
    sessions, result = poll(
        adapter, clock, clock.event("pre_llm_call", session_id="p", turn_id="t1"),
        clock.event("subagent_start", parent_session_id="p", child_session_id="c",
                    child_role="researcher"),
        clock.event("pre_llm_call", session_id="c", turn_id="c1"),
        clock.event("pre_llm_call", session_id="branch", turn_id="b1"),
        clock.event("pre_llm_call", session_id="backfilled", turn_id="x1"),
        clock.event("pre_llm_call", session_id="f", turn_id="f1"),
    )
    assert sessions["p"].title == "Main chat"
    assert (sessions["f"].title, sessions["f"].cwd) == ("Factory run", "/work/grove")
    assert (sessions["c"].parent_id, sessions["c"].title) == ("p", "researcher")
    assert sessions["backfilled"].parent_id == "p"  # restart: marker from the saved session
    assert sessions["branch"].parent_id is None  # a branch is its own session

    sessions, result = poll(
        adapter, clock,
        clock.event("post_llm_call", session_id="c", turn_id="c1", response="child report"),
        clock.event("on_session_end", session_id="c", turn_id="c1", completed=True),
        clock.event("subagent_stop", parent_session_id="p", child_session_id="c"),
    )
    assert sessions["c"].state == "idle" and result.completions == []

    restored = HermesAdapter(tmp_path, json.loads(json.dumps(adapter.checkpoint())))
    assert poll(restored, clock)[0]["c"].parent_id == "p"
    sessions, _ = poll(restored, clock, clock.event("on_session_finalize", session_id="p"))
    assert "p" not in sessions and "c" not in sessions  # helpers never outlive their parent row


def test_sessions_of_a_dead_process_disappear(tmp_path, clock):
    adapter = HermesAdapter(tmp_path)
    started = clock.event("pre_llm_call", session_id="s", turn_id="t1") | {"pid": 2**22 + 12345}
    assert poll(adapter, clock, started)[0] == {}


def test_plugin_writes_bounded_fields_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("CREW_HOME", str(tmp_path))
    fake = types.ModuleType("hermes_cli.plugins")
    fake.VALID_HOOKS = {"pre_llm_call", "post_llm_call", "on_session_end", "pre_tool_call"}
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", fake)
    import crew.hermes_plugin as plugin

    plugin = importlib.reload(plugin)
    hooks = {}
    ctx = types.SimpleNamespace(register_hook=lambda name, fn: hooks.__setitem__(name, fn))
    plugin.register(ctx)
    assert set(hooks) == fake.VALID_HOOKS  # absent observers are skipped, not assumed

    assert hooks["pre_tool_call"](session_id="s", tool_name="terminal",
                                  args={"command": "cat ~/.ssh/id_ed25519"}) is None
    assert hooks["post_llm_call"](session_id="s", turn_id="t", assistant_response="Final",
                                  conversation_history=["private"], user_message="private") is None
    events = Journal(tmp_path / "journal.jsonl").read()
    assert [e["event"] for e in events] == ["plugin_loaded", "pre_tool_call", "post_llm_call"]
    assert events[2]["response"] == "Final" and events[1]["tool_name"] == "terminal"
    assert "private" not in json.dumps(events) and "id_ed25519" not in json.dumps(events)

    adapter = HermesAdapter(tmp_path)  # the adapter consumes exactly what the plugin wrote
    assert [s.session_id for s in adapter.poll(events, time.time()).sessions] == ["s"]

    def removed():
        raise FileNotFoundError("the working folder was deleted")

    monkeypatch.setattr(plugin.os, "getcwd", removed)
    assert hooks["pre_tool_call"](session_id="s", tool_name="terminal") is None
    assert "cwd" not in Journal(tmp_path / "journal.jsonl").read()[-1]

    (tmp_path / "journal.jsonl").unlink()
    (tmp_path / "journal.jsonl").mkdir()
    assert hooks["pre_tool_call"](session_id="s", tool_name="terminal") is None
    assert Journal(tmp_path / "journal.jsonl").take_errors() == {"hermes": 1}
