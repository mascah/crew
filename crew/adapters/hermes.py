"""Hermes Agent: everything arrives from the in-process observer plugin.

`pre_llm_call` opens a turn, `post_llm_call` carries its response and the
canonical `on_session_end` closes it with outcome flags. Human waits come only
from the paired human-input observers; where the installed Hermes lacks them
the adapter says so instead of inferring waits from tool names.
"""

import contextlib
import json
import sqlite3
from pathlib import Path

from crew.adapters import RETAIN_SECONDS, Result, pid_alive
from crew.model import CompletionObs, SessionObs

IDLE_SHOWN_SECONDS = 3600.0
WAIT_KINDS = {"clarify": "Waiting for an answer"}
NO_WAITS = "Installed Hermes lacks human-input observers: waits are not observed"


class HermesAdapter:
    harness = "hermes"

    def __init__(self, home: Path, state: dict | None = None):
        self.home = home
        state = state or {}
        self.sessions: dict[str, dict] = state.get("sessions", {})
        self.hooks: list[str] | None = state.get("hooks")

    def checkpoint(self) -> dict:
        return {"sessions": self.sessions, "hooks": self.hooks}

    def _session(self, sid: str, event: dict) -> dict:
        ts = event.get("ts_ns", 0) / 1e9
        s = self.sessions.setdefault(sid, {
            "turn": None, "activity": None, "waits": {}, "response": None, "parent": None,
            "title": None, "cwd": None, "known": False,
        })
        s["at"], s["pid"] = ts, event.get("pid") or s.get("pid")
        if not s["known"]:  # retried until Hermes has saved the session
            s["known"] = self._lookup(sid, s, event)
        return s

    def _lookup(self, sid: str, s: dict, event: dict) -> bool:
        """Saved identity from Hermes's own session store, opened read-only."""
        home = Path(event.get("hermes_home") or self.home)
        if event.get("platform") == "cli":
            s["cwd"] = event.get("cwd")
        # One gateway serves every profile, so the session may be saved in any of them.
        for store in [home / "state.db", *sorted(home.glob("profiles/[!.]*/state.db"))]:
            with contextlib.suppress(sqlite3.Error, OSError, ValueError):
                db = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=0.2)
                try:
                    row = db.execute(
                        "SELECT cwd, git_repo_root, title, parent_session_id, model_config"
                        " FROM sessions WHERE id = ?", (sid,),
                    ).fetchone()
                finally:
                    db.close()
                if row:
                    s["cwd"] = row[0] or row[1] or s["cwd"]
                    s["title"] = row[2]
                    # A parent link alone can be a branch or reset; delegation is marked.
                    config = json.loads(row[4] or "{}")
                    if row[3] and config.get("_delegate_from") == row[3]:
                        s["parent"] = s["parent"] or row[3]
                    return True
        return False

    def _apply(self, event: dict, result: Result) -> None:
        name, sid = event.get("event"), event.get("session_id")
        if name == "plugin_loaded":
            self.hooks = event.get("hooks") or []
        elif name == "subagent_start" and event.get("child_session_id"):
            child = self._session(event["child_session_id"], event)
            child["parent"] = event.get("parent_session_id")
            child["title"] = child["title"] or event.get("child_role")
            child["turn"] = child["turn"] or "delegated"
        elif name == "subagent_stop" and event.get("child_session_id"):
            child = self._session(event["child_session_id"], event)
            child["turn"], child["activity"], child["waits"] = None, None, {}
        elif name == "on_session_reset":
            self.sessions.pop(event.get("old_session_id") or sid or "", None)
        elif not sid:
            return
        elif name == "on_session_finalize":
            self.sessions.pop(sid, None)
        elif name == "on_session_start":
            self._session(sid, event)
        elif name == "pre_llm_call":
            s = self._session(sid, event)
            s.update(turn=event.get("turn_id"), activity=None, response=None, waits={})
        elif name == "pre_tool_call":
            self._session(sid, event)["activity"] = f"Using {event.get('tool_name') or 'a tool'}"
        elif name == "post_llm_call":
            s = self._session(sid, event)
            s["response"], s["activity"] = event.get("response"), "Writing a response"
        elif name == "on_human_input_request":
            s = self._session(sid, event)
            reason = WAIT_KINDS.get(event.get("kind", ""), "Waiting for approval")
            s["waits"][str(event.get("request_id"))] = reason
        elif name == "on_human_input_resolved":
            self._session(sid, event)["waits"].pop(str(event.get("request_id")), None)
        elif name == "on_session_end":
            s = self._session(sid, event)
            turn, response = event.get("turn_id") or s["turn"], s["response"]
            finished = event.get("completed") and not event.get("failed")
            if finished and not event.get("interrupted") and turn and response and not s["parent"]:
                result.completions.append(
                    CompletionObs(
                        harness="hermes", session_id=sid, request_id=str(turn), response=response,
                        completed_at=event.get("ts_ns", 0) / 1e9, title=s["title"], cwd=s["cwd"],
                    )
                )
            s["turn"], s["activity"], s["response"], s["waits"] = None, None, None, {}

    def poll(self, events: list[dict], now: float) -> Result:
        result = Result()
        for event in events:
            self._apply(event, result)
        if self.hooks is not None and "on_human_input_request" not in self.hooks:
            result.gaps.append(NO_WAITS)
        for sid, s in list(self.sessions.items()):
            if not pid_alive(s.get("pid")) or now - s["at"] > RETAIN_SECONDS:
                del self.sessions[sid]  # the Hermes process that owned it is gone
        for sid, s in self.sessions.items():
            parent = s["parent"] if s["parent"] in self.sessions else None
            if s["parent"] and not parent:
                continue  # a helper is only shown beneath its evidenced parent
            if s["waits"]:
                state, activity = "waiting", next(iter(s["waits"].values()))
            elif s["turn"]:
                state, activity = "working", s["activity"]
            elif now - s["at"] <= IDLE_SHOWN_SECONDS:
                state, activity = "idle", None
            else:
                continue
            result.sessions.append(
                SessionObs(
                    harness="hermes", session_id=sid, parent_id=parent, state=state,
                    activity=activity, title=s["title"], cwd=s["cwd"],
                    request_id=str(s["turn"]) if s["turn"] else None, observed_at=s["at"],
                )
            )
        return result
