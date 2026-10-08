import importlib
import json
import os
import sqlite3
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from threading import Barrier

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


def saved_session(home, sid, *, cwd=None, repo=None, title=None):
    home.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(home / "state.db") as db:
        db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT, cwd TEXT, git_repo_root TEXT,"
                   " title TEXT, parent_session_id TEXT, model_config TEXT)")
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)", (sid, cwd, repo, title, None, None))


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


@pytest.fixture
def scoped_plugin(tmp_path, monkeypatch):
    """Hermes's context-local API boundary, without models or real session data."""
    monkeypatch.setenv("CREW_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "gateway"))
    monkeypatch.setenv("TERMINAL_CWD", "/wrong/process/workspace")
    home = ContextVar("test_hermes_home", default=tmp_path / "gateway")
    policy = ContextVar("test_terminal_policy", default=None)
    cwd = ContextVar("test_session_cwd", default="")
    plugins = types.ModuleType("hermes_cli.plugins")
    plugins.VALID_HOOKS = set(ALL_HOOKS) | {"on_session_start", "pre_tool_call"}
    constants = types.ModuleType("hermes_constants")
    constants.get_hermes_home = home.get
    terminal = types.ModuleType("tools.terminal_scope")

    def terminal_env(name, default=""):
        values = policy.get() or {}
        if isinstance(values, Exception):
            raise values
        return values.get(name, default)

    terminal.terminal_env = terminal_env
    runtime = types.ModuleType("agent.runtime_cwd")
    runtime.scoped_session_cwd = cwd.get
    for name, module in {
        "hermes_cli": types.ModuleType("hermes_cli"), "hermes_cli.plugins": plugins,
        "hermes_constants": constants, "tools": types.ModuleType("tools"),
        "tools.terminal_scope": terminal, "agent": types.ModuleType("agent"),
        "agent.runtime_cwd": runtime,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    import crew.hermes_plugin as plugin

    plugin = importlib.reload(plugin)
    hooks = {}
    ctx = types.SimpleNamespace(register_hook=lambda name, fn: hooks.__setitem__(name, fn))
    plugin.register(ctx)
    return hooks, home, policy, cwd


def test_plugin_captures_concurrent_routed_profile_workspaces(tmp_path, scoped_plugin):
    hooks, home, policy, _ = scoped_plugin
    barrier = Barrier(2)

    def observe(profile, workspace):
        home.set(tmp_path / "profiles" / profile)
        policy.set({"TERMINAL_ENV": "local", "TERMINAL_CWD": workspace})
        barrier.wait(timeout=5)
        assert hooks["pre_llm_call"](session_id=profile, turn_id="t", platform="discord") is None

    with ThreadPoolExecutor(max_workers=2) as executor:
        profiles = [("keyborg-factory", "keyborg"), ("grove-factory", "grove")]
        futures = [executor.submit(observe, profile, f"/checkouts/{workspace}")
                   for profile, workspace in profiles]
        for future in futures:
            future.result()
    events = {e["session_id"]: e for e in Journal(tmp_path / "journal.jsonl").read()
              if e.get("session_id")}
    assert {sid: (e["hermes_home"], e.get("cwd")) for sid, e in events.items()} == {
        "keyborg-factory": (str(tmp_path / "profiles/keyborg-factory"), "/checkouts/keyborg"),
        "grove-factory": (str(tmp_path / "profiles/grove-factory"), "/checkouts/grove"),
    }
    for sid in events:
        saved_session(tmp_path / "profiles" / sid, sid)
    adapter = HermesAdapter(tmp_path)
    sessions = adapter.poll(list(events.values()), time.time()).sessions
    assert {s.session_id: s.cwd for s in sessions} == {
        "keyborg-factory": "/checkouts/keyborg", "grove-factory": "/checkouts/grove",
    }


def test_fresh_workspace_updates_a_known_session_across_restart(tmp_path, clock):
    profile = tmp_path / "profiles/keyborg-factory"
    saved_session(profile, "s")
    adapter = HermesAdapter(tmp_path)
    sessions, result = poll(
        adapter, clock,
        clock.event("pre_llm_call", session_id="s", turn_id="old", platform="discord"),
        clock.event("post_llm_call", session_id="s", response="Old response", platform="discord"),
        clock.event("on_session_end", session_id="s", completed=True, platform="discord"),
    )
    assert sessions["s"].cwd is None and result.completions[0].cwd is None
    restored = HermesAdapter(tmp_path, json.loads(json.dumps(adapter.checkpoint())))
    sessions, fresh = poll(restored, clock, clock.event(
        "pre_llm_call", session_id="s", turn_id="new", platform="discord",
        hermes_home=str(profile), cwd="/checkouts/keyborg", cwd_source="terminal",
        terminal_backend="local",
    ))
    assert list(sessions) == ["s"] and sessions["s"].cwd == "/checkouts/keyborg"
    assert sessions["s"].request_id == "new" and fresh.completions == []
    (profile / "config.yaml").write_text("terminal:\n  cwd: /different/today\n")
    assert poll(restored, clock)[0]["s"].cwd == "/checkouts/keyborg"
    assert result.completions[0].cwd is None  # prior completions never use today's config


@pytest.mark.parametrize(("source", "expected"), [
    ("terminal", "/saved/session"), ("cli", "/saved/session"), ("runtime", "/live/override"),
])
def test_native_and_runtime_overrides_beat_profile_cwd(tmp_path, clock, source, expected):
    saved_session(tmp_path, "s", cwd="/saved/session")
    sessions, _ = poll(HermesAdapter(tmp_path), clock, clock.event(
        "pre_llm_call", session_id="s", turn_id="t", platform="discord",
        cwd="/live/override", cwd_source=source, terminal_backend="local",
    ))
    assert sessions["s"].cwd == expected


def test_saved_workspace_can_arrive_after_a_session_row(tmp_path, clock):
    saved_session(tmp_path, "s")
    adapter = HermesAdapter(tmp_path)
    assert poll(adapter, clock, clock.event(
        "on_session_start", session_id="s", platform="discord"))[0]["s"].cwd is None
    with sqlite3.connect(tmp_path / "state.db") as db:
        db.execute("UPDATE sessions SET cwd = ?, title = ? WHERE id = ?",
                   ("/saved/late", "Named later", "s"))
    sessions, _ = poll(adapter, clock, clock.event(
        "pre_llm_call", session_id="s", turn_id="t", platform="discord"))
    assert (sessions["s"].cwd, sessions["s"].title) == ("/saved/late", "Named later")


def test_discovered_owner_discards_an_out_of_scope_profile_workspace(tmp_path, clock):
    adapter = HermesAdapter(tmp_path)
    metadata = {"hermes_home": str(tmp_path), "cwd": "/gateway/profile/work",
                "cwd_source": "terminal", "terminal_backend": "local"}
    poll(adapter, clock, clock.event("on_session_start", session_id="s", platform="discord",
                                   **metadata))
    saved_session(tmp_path / "profiles/actual-owner", "s")
    sessions, _ = poll(adapter, clock, clock.event("pre_llm_call", session_id="s", turn_id="t",
                                                  platform="discord", **metadata))
    assert sessions["s"].cwd is None


def test_native_profiles_beneath_an_event_home_are_still_discovered(tmp_path, clock):
    external = tmp_path / "external"
    saved_session(external / "profiles/routed", "s", cwd="/native/profile/work")
    sessions, _ = poll(HermesAdapter(tmp_path / "configured"), clock, clock.event(
        "pre_llm_call", session_id="s", turn_id="t", platform="discord",
        hermes_home=str(external),
    ))
    assert sessions["s"].cwd == "/native/profile/work"


def test_terminal_workspace_requires_an_identified_profile(tmp_path, clock):
    sessions, _ = poll(HermesAdapter(tmp_path), clock, clock.event(
        "pre_llm_call", session_id="s", turn_id="t", platform="discord",
        cwd="/unowned/workspace", cwd_source="terminal", terminal_backend="local",
    ))
    assert sessions["s"].cwd is None


@pytest.mark.parametrize("backend", ["ssh", "docker", "unknown"])
def test_nonlocal_or_unavailable_workspace_is_not_a_host_project(tmp_path, clock, backend):
    saved_session(tmp_path, "s", cwd="/remote/work")
    sessions, _ = poll(HermesAdapter(tmp_path), clock, clock.event(
        "pre_llm_call", session_id="s", turn_id="t", platform="discord",
        terminal_backend=backend, cwd="/gateway/work", cwd_source="terminal",
    ))
    assert sessions["s"].cwd is None


@pytest.mark.parametrize(("policy_value", "runtime_cwd"), [
    ({"TERMINAL_ENV": "ssh", "TERMINAL_CWD": "/remote/work"}, "/remote/session"),
    ({"TERMINAL_ENV": "docker", "TERMINAL_CWD": "/work"}, ""),
    ({"TERMINAL_ENV": "local", "TERMINAL_CWD": "."}, ""),
    ({"TERMINAL_ENV": "local", "TERMINAL_CWD": "auto"}, ""),
    ({"TERMINAL_ENV": "local", "TERMINAL_CWD": "cwd"}, ""),
    ({"TERMINAL_ENV": "local", "TERMINAL_CWD": "relative"}, ""),
    ({}, ""), (RuntimeError("policy unavailable"), ""),
])
def test_plugin_leaves_unresolved_workspaces_unknown(tmp_path, scoped_plugin,
                                                   policy_value, runtime_cwd):
    hooks, _, policy, cwd = scoped_plugin
    policy.set(policy_value)
    cwd.set(runtime_cwd)
    assert hooks["pre_llm_call"](session_id="s", turn_id="t", platform="discord") is None
    [event] = [e for e in Journal(tmp_path / "journal.jsonl").read() if e.get("session_id")]
    assert "cwd" not in event and "cwd_source" not in event
    assert HermesAdapter(tmp_path).poll([event], time.time()).sessions[0].cwd is None


def test_plugin_preserves_session_and_cli_workspace_overrides(tmp_path, scoped_plugin, monkeypatch):
    hooks, _, policy, cwd = scoped_plugin
    policy.set({"TERMINAL_ENV": "local", "TERMINAL_CWD": "/profile/work"})
    cwd.set("/session/override")
    hooks["pre_llm_call"](session_id="session", turn_id="t", platform="discord")
    cwd.set("")
    policy.set({"TERMINAL_ENV": "local"})
    monkeypatch.chdir(tmp_path)
    hooks["pre_llm_call"](session_id="cli", turn_id="t", platform="cli")
    events = [e for e in Journal(tmp_path / "journal.jsonl").read() if e.get("session_id")]
    assert [e["cwd"] for e in events] == ["/session/override", str(tmp_path)]
    sessions = HermesAdapter(tmp_path).poll(events, time.time()).sessions
    assert {s.session_id: s.cwd for s in sessions} == {
        "session": "/session/override", "cli": str(tmp_path),
    }


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

    saved_session(tmp_path, "cli")
    hooks["pre_llm_call"](session_id="cli", turn_id="t", platform="cli")
    [event] = Journal(tmp_path / "journal.jsonl").read()[-1:]
    sessions = adapter.poll([event], time.time()).sessions
    assert {s.session_id: s.cwd for s in sessions}["cli"] == os.getcwd()

    def removed():
        raise FileNotFoundError("the working folder was deleted")

    monkeypatch.setattr(plugin.os, "getcwd", removed)
    assert hooks["pre_tool_call"](session_id="s", tool_name="terminal") is None
    assert "cwd" not in Journal(tmp_path / "journal.jsonl").read()[-1]

    (tmp_path / "journal.jsonl").unlink()
    (tmp_path / "journal.jsonl").mkdir()
    assert hooks["pre_tool_call"](session_id="s", tool_name="terminal") is None
    assert Journal(tmp_path / "journal.jsonl").take_errors() == {"hermes": 1}
