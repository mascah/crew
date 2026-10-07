"""Claude Code: transcripts for requests, activity and responses; the live
session registry and hook journal for liveness and human waits.

Settlement is surface-specific. The TUI writes `system:turn_duration` once a
request (including stop-hook continuation) has settled. Hosted sessions never
write it, so a `stop_hook_summary` settles only once the session ends, the
next prompt arrives, or the transcript has stayed quiet for SETTLE_GRACE. A
continuing stop hook writes its feedback record before that summary, which
disarms it.
"""

import contextlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from crew.adapters import RETAIN_SECONDS, Result, epoch, pid_alive, short
from crew.journal import Journal
from crew.model import CompletionObs, SessionObs

SETTLE_GRACE = 10.0
DISCOVER_EVERY = 5.0
HOT_SECONDS = 3600.0  # transcripts re-read every poll after recent activity
UNKNOWN_AFTER = 120.0  # unobserved liveness: quiet this long is not "working"
HOOK_LIVE_SECONDS = 12 * 3600.0
MAX_HELPERS = 20
WAIT_NOTIFICATIONS = {
    "permission_prompt": "Waiting for permission",
    "elicitation_dialog": "Waiting for input",
}
NOT_A_PROMPT = ("<local-command-", "<bash-", "<command-name>", "<command-message>")


@dataclass
class Thread:
    """One transcript: a main session, or a helper when agent_id is set."""

    path: str
    session_id: str
    agent_id: str | None = None
    offset: int = 0
    cwd: str | None = None
    title: str | None = None
    entrypoint: str | None = None
    request_id: str | None = None
    request_started: float = 0.0
    last_user: str | None = None
    message_id: str | None = None
    text: str = ""  # text of the latest assistant message
    end_turn: bool = False
    failed: bool = False
    activity: str | None = None
    pending: dict[str, str] = field(default_factory=dict)  # tool_use id -> name
    stop_at: float | None = None
    last_ts: float = 0.0
    parent_agent: str | None = None  # helpers: nested parent from metadata
    meta_read: bool = False
    handed_back: bool = False  # helpers: final report delivered through SubagentHandback
    done: list[tuple[str, float, str]] = field(default_factory=list)  # not checkpointed


def describe(name: str, args: dict) -> str:
    base = os.path.basename(str(args.get("file_path") or args.get("notebook_path") or ""))
    if name == "Bash":
        return short(args.get("description") or f"Running {args.get('command', 'a command')}")
    if name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        return f"Editing {base}" if base else "Editing a file"
    if name == "Read":
        return f"Reading {base}" if base else "Reading a file"
    if name in ("Grep", "Glob"):
        return short(f"Searching for {args.get('pattern', 'files')}")
    if name in ("Agent", "Task"):
        return short(f"Delegating: {args.get('description', 'a helper')}")
    if name == "AskUserQuestion":
        return "Asking a question"
    if name.startswith("mcp__"):
        return short("Using " + " ".join(name.split("__")[1:]))
    return f"Using {name}"


def _text(content: object) -> str | None:
    """Prompt text of a user record, or None for tool results."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def advance(t: Thread, r: dict) -> None:
    ts = epoch(r.get("timestamp"), t.last_ts)
    t.last_ts = max(t.last_ts, ts)
    t.cwd = r.get("cwd") or t.cwd
    t.entrypoint = r.get("entrypoint") or t.entrypoint
    kind = r.get("type")
    if kind in ("ai-title", "custom-title"):
        t.title = r.get("aiTitle") or r.get("customTitle") or t.title
    elif kind == "user":
        message = r.get("message") or {}
        text = _text(message.get("content"))
        if text is None:  # tool results: the request continues
            t.stop_at = None
            for block in message["content"]:
                if isinstance(block, dict):
                    t.pending.pop(block.get("tool_use_id", ""), None)
            if t.request_id is None:
                _open(t, t.last_user or r.get("uuid", ""), ts)
        elif text.lstrip().startswith("[Request interrupted"):
            _close(t)
        elif text.lstrip().startswith(NOT_A_PROMPT):
            t.last_user = r.get("uuid")
        elif r.get("isMeta") and (t.request_id or text.lstrip().startswith("Stop hook feedback")):
            # Injected mid-request (stop-hook feedback): the model answers again,
            # so the stop summary that follows must not settle the request.
            if t.request_id is None:  # settled during a slow stop hook: the same request goes on
                _open(t, t.last_user or r.get("uuid", ""), ts)
            t.end_turn, t.stop_at = False, None
        else:
            _settle_stopped(t)  # a new prompt follows a stopped request
            _open(t, r.get("uuid", ""), ts)
    elif kind == "assistant":
        message = r.get("message") or {}
        if t.request_id is None:
            _open(t, t.last_user or r.get("uuid", ""), ts)
        t.stop_at = None
        if message.get("id") != t.message_id:
            t.message_id, t.text = message.get("id"), ""
        content = message.get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                t.text += block.get("text", "")
                t.activity = "Writing a response"
            elif block.get("type") == "tool_use":
                t.pending[block.get("id", "")] = block.get("name", "")
                t.handed_back = t.handed_back or block.get("name") == "SubagentHandback"
                t.activity = describe(block.get("name", ""), block.get("input") or {})
        t.end_turn = message.get("stop_reason") == "end_turn"
        t.failed = t.failed or bool(r.get("isApiErrorMessage"))
        if t.end_turn:  # settles on turn_duration, or after a quiet period where none is written
            t.stop_at = ts
    elif kind == "system" and r.get("subtype") == "turn_duration":
        _settle(t, ts)
    elif kind == "system" and r.get("subtype") == "stop_hook_summary" and t.end_turn:
        t.stop_at = ts


def _open(t: Thread, request_id: str, ts: float) -> None:
    t.request_id, t.request_started, t.last_user = request_id, ts, request_id
    t.text, t.message_id, t.end_turn, t.failed = "", None, False, False
    t.activity, t.stop_at, t.handed_back = None, None, False
    t.pending.clear()


def _close(t: Thread) -> None:
    t.request_id, t.activity, t.stop_at = None, None, None
    t.pending.clear()


def _settle(t: Thread, ts: float) -> None:
    """A settled request finishes only with a delivered, non-error response."""
    if t.request_id and t.end_turn and not t.failed and t.text.strip():
        t.done.append((t.request_id, ts, t.text))
    _close(t)


def _settle_stopped(t: Thread) -> None:
    """Settle a response that ended its turn with no `turn_duration` to confirm it."""
    if t.stop_at is not None:
        _settle(t, t.stop_at)


class ClaudeAdapter:
    harness = "claude"

    def __init__(self, home: Path, state: dict | None = None):
        self.home = home
        state = state or {}
        self.threads = {p: Thread(**v) for p, v in state.get("threads", {}).items()}
        # session_id -> {"live": bool, "at": ts, "wait": [ts, reason] | None}
        self.hooked: dict[str, dict] = state.get("hooked", {})
        self.helper_stops: dict[str, float] = state.get("helper_stops", {})
        self._discovered = 0.0
        self._errors: list[str] = []

    def checkpoint(self) -> dict:
        threads = {}
        for path, t in self.threads.items():
            threads[path] = asdict(t) | {"done": []}
        return {"threads": threads, "hooked": self.hooked, "helper_stops": self.helper_stops}

    # --- evidence intake ---

    def _discover(self, now: float) -> None:
        cutoff = now - RETAIN_SECONDS
        seen = set()
        projects = self.home / "projects"
        for pattern, helper in (("*/*.jsonl", False), ("*/*/subagents/agent-*.jsonl", True)):
            for path in projects.glob(pattern):
                key = str(path)
                with contextlib.suppress(OSError):
                    if path.stat().st_mtime < cutoff:
                        continue  # untouched for the whole history window: no longer tracked
                    seen.add(key)
                    if key in self.threads:
                        continue
                    if helper:
                        agent = path.stem.removeprefix("agent-")
                        self.threads[key] = Thread(key, path.parts[-3], agent_id=agent)
                    else:
                        self.threads[key] = Thread(key, path.stem)
        for key in [k for k in self.threads if k not in seen]:
            del self.threads[key]

    def _read(self, t: Thread) -> None:
        tail = Journal(Path(t.path), t.offset)
        try:
            for record in tail.records():
                try:
                    advance(t, record)
                except Exception as error:  # an unexpected shape costs one record, not the adapter
                    self._errors.append(
                        f"{os.path.basename(t.path)}: skipped a record ({type(error).__name__})")
        except OSError as error:
            self._errors.append(f"{os.path.basename(t.path)}: {error}")
        t.offset = tail.offset

    def _registry(self) -> dict[str, dict]:
        """Live interactive sessions by id, from Claude's own pid files."""
        live = {}
        for path in (self.home / "sessions").glob("*.json"):
            with contextlib.suppress(OSError, ValueError):
                entry = json.loads(path.read_text())
                if isinstance(entry, dict) and pid_alive(entry.get("pid")) and entry.get(
                        "sessionId"):
                    live[str(entry["sessionId"])] = entry
        return live

    def _apply(self, event: dict) -> None:
        sid, name = event.get("session_id"), event.get("hook_event_name")
        if not sid:
            return
        ts = event.get("ts_ns", 0) / 1e9
        hooked = self.hooked.setdefault(sid, {"live": None, "at": ts, "wait": None})
        hooked["at"] = ts
        hooked["cwd"] = event.get("cwd") or hooked.get("cwd")
        if name == "SessionStart":
            hooked["live"] = True
        elif name == "SessionEnd":
            hooked["live"], hooked["wait"] = False, None
        elif name == "Notification":
            if reason := WAIT_NOTIFICATIONS.get(event.get("notification_type", "")):
                hooked["wait"] = [ts, reason]
        elif name == "Elicitation":
            hooked["wait"] = [ts, "Waiting for input"]
        elif name in ("ElicitationResult", "Stop", "UserPromptSubmit"):
            hooked["wait"] = None
        elif name == "StopFailure":
            for t in self.threads.values():
                if t.session_id == sid and t.agent_id is None:
                    t.failed = True
        elif name == "SubagentStop" and event.get("agent_id"):
            self.helper_stops[f"{sid}/{event['agent_id']}"] = ts
        elif name == "SubagentStart" and event.get("agent_id"):
            self.helper_stops.pop(f"{sid}/{event['agent_id']}", None)
        if hooked["live"] is None and name != "SessionEnd":
            hooked["live"] = True  # any callback proves the session was running

    # --- observations ---

    def poll(self, events: list[dict], now: float) -> Result:
        self._errors = []
        if now - self._discovered >= DISCOVER_EVERY:
            self._discover(now)
            self._discovered = now
        for event in events:
            self._apply(event)
        poked = {e.get("transcript_path") for e in events}
        for key, t in self.threads.items():
            if key in poked or t.offset == 0 or now - t.last_ts < HOT_SECONDS:
                self._read(t)
            else:  # cold: a size change makes it hot again
                with contextlib.suppress(OSError):
                    if os.path.getsize(key) != t.offset:
                        self._read(t)

        has_registry = (self.home / "sessions").is_dir()
        registry = self._registry()
        mains = {t.session_id: t for t in self.threads.values() if t.agent_id is None}
        helpers: dict[str, list[Thread]] = {}
        for t in self.threads.values():
            if t.agent_id:
                t.done.clear()  # helper turns are not the author's requests
                helpers.setdefault(t.session_id, []).append(t)

        result = Result(gaps=self._errors)
        for sid in mains.keys() | registry.keys() | self.hooked.keys():
            entry, hooked = registry.get(sid), self.hooked.get(sid)
            t = mains.get(sid) or Thread(  # live before its first transcript record
                "", sid, entrypoint="cli" if entry else None, cwd=(hooked or {}).get("cwd")
            )
            if hooked and (hooked["live"] is not True or now - hooked["at"] > HOOK_LIVE_SECONDS):
                hooked = None
            # The registry is authoritative for the TUI; hooks cover other surfaces.
            interactive = has_registry and t.entrypoint == "cli"
            live = bool(entry) or (bool(hooked) and not interactive)
            ended = not live and (interactive or sid in self.hooked)
            quiet = now - t.last_ts >= SETTLE_GRACE and (entry or {}).get("status") != "busy"
            if ended or quiet:
                _settle_stopped(t)
            for request_id, completed_at, response in t.done:
                result.completions.append(
                    CompletionObs(
                        harness="claude", session_id=sid, request_id=request_id,
                        completed_at=completed_at, response=response, title=t.title, cwd=t.cwd,
                    )
                )
            t.done.clear()
            if ended:
                continue
            obs = self._main(t, entry, hooked if live else None, helpers.get(sid, []), now)
            if obs is None:
                continue
            result.sessions.append(obs)
            recent = [  # this request's helpers, and any still running from an earlier one
                h for h in helpers.get(sid, [])
                if h.last_ts >= t.request_started
                or (self._running(h) and now - h.last_ts < HOT_SECONDS)
            ]
            for h in sorted(recent, key=lambda h: h.last_ts)[-MAX_HELPERS:]:
                result.sessions.append(self._helper(h, t, now))

        for sid in [s for s, h in self.hooked.items() if now - h["at"] > RETAIN_SECONDS]:
            del self.hooked[sid]
        for key in [k for k, at in self.helper_stops.items() if now - at > RETAIN_SECONDS]:
            del self.helper_stops[key]
        return result

    def _main(
        self, t: Thread, entry: dict | None, hooked: dict | None, helpers: list[Thread], now: float
    ) -> SessionObs | None:
        entry = entry or {}
        status, updated = entry.get("status"), entry.get("statusUpdatedAt")
        status_at = updated / 1000 if isinstance(updated, (int, float)) else 0.0
        records_at = max([t.last_ts, *(h.last_ts for h in helpers)])
        wait = hooked["wait"] if hooked else None
        if wait and max(records_at, status_at) > wait[0]:
            wait = hooked["wait"] = None  # type: ignore[index]  # later native evidence
        gap = None
        if status == "waiting":
            state, activity = "waiting", short(f"Waiting: {entry.get('waitingFor') or 'input'}")
        elif wait:
            state, activity = "waiting", wait[1]
            if not entry:
                gap = "Wait closes on the next native record"
        elif "AskUserQuestion" in t.pending.values():
            state, activity = "waiting", "Waiting for an answer"
        elif status == "busy" or (status != "idle" and t.request_id):
            state, activity = "working", t.activity
            if not entry and not hooked:
                gap = "Liveness not observed for this session"
                if now - t.last_ts > HOT_SECONDS:
                    return None
                if now - t.last_ts > UNKNOWN_AFTER:
                    state = "unknown"
            elif not entry and now - t.last_ts > UNKNOWN_AFTER:
                gap = "No evidence since its last record: still running or killed look alike"
        elif entry or hooked:
            state, activity = "idle", None
        else:
            return None  # no request and no liveness evidence: history, not activity
        return SessionObs(
            harness="claude", session_id=t.session_id, state=state, activity=activity,
            title=t.title or entry.get("name"), cwd=t.cwd or entry.get("cwd"),
            request_id=t.request_id,
            observed_at=max(t.last_ts, status_at, hooked["at"] if hooked else 0.0) or now, gap=gap,
        )

    def _running(self, h: Thread) -> bool:
        stopped = self.helper_stops.get(f"{h.session_id}/{h.agent_id}", 0.0) >= h.last_ts
        return not (stopped or h.handed_back or (h.end_turn and not h.pending))

    def _helper(self, h: Thread, parent: Thread, now: float) -> SessionObs:
        key = f"{h.session_id}/{h.agent_id}"
        if not h.meta_read:
            h.meta_read = True
            with contextlib.suppress(OSError, ValueError):
                meta = json.loads(Path(h.path).with_suffix(".meta.json").read_text())
                h.title = meta.get("description") or meta.get("agentType")
                h.parent_agent = meta.get("parentAgentId")
        working = self._running(h)
        state, gap = ("working" if working else "idle"), None
        outlived = not parent.request_id or h.last_ts < parent.request_started
        if working and now - h.last_ts > UNKNOWN_AFTER and outlived:
            state, gap = "unknown", "No recent helper evidence"
        return SessionObs(
            harness="claude", session_id=key, state=state, title=h.title,
            parent_id=f"{h.session_id}/{h.parent_agent}" if h.parent_agent else h.session_id,
            activity=h.activity if working else None, cwd=h.cwd or parent.cwd,
            observed_at=h.last_ts or now, gap=gap,
        )
