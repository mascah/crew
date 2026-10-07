"""Codex CLI: daemon runtime status for loaded threads; rollouts for requests,
activity, responses and backfill.

The daemon is only ever read (`thread/loaded/list`, `thread/read`): nothing
here resumes a thread, starts a turn or answers a request. Threads outside
the daemon keep their rollout-derived request state, with human waits and,
without hooks, liveness reported as an explicit gap.
"""

import base64
import contextlib
import json
import os
import re
import socket
import struct
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from crew.adapters import RETAIN_SECONDS, Result, epoch, short
from crew.journal import Journal
from crew.model import CompletionObs, SessionObs

DISCOVER_EVERY = 5.0
RECONNECT_EVERY = 10.0
CALL_SECONDS = 4.0
HOT_SECONDS = 3600.0
UNKNOWN_AFTER = 120.0
HOOK_LIVE_SECONDS = 12 * 3600.0
MAX_HELPERS = 20
WAIT_FLAGS = {
    "waitingOnApproval": "Waiting for approval",
    "waitingOnUserInput": "Waiting for an answer",
}
OUTSIDE_DAEMON = "Liveness and human waits not observed outside the Codex daemon"


class Daemon:
    """Read-only JSON-RPC over the daemon's Unix WebSocket."""

    def __init__(self, path: Path, timeout: float = 2.0):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(str(path))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        header = bytearray()
        while b"\r\n\r\n" not in header:
            header += self._recv(1)
        if not header.startswith(b"HTTP/1.1 101"):
            raise ConnectionError("Codex daemon rejected the WebSocket upgrade")
        self.calls = 0
        client = {"name": "crew_collector", "title": "Crew read-only observer", "version": "0.1.0"}
        self.call("initialize", {"clientInfo": client, "capabilities": {"experimentalApi": True}})
        self._send({"method": "initialized"})

    def _recv(self, n: int) -> bytes:
        data = bytearray()
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Codex daemon closed the connection")
            data += chunk
        return bytes(data)

    def _send(self, message: dict | bytes, opcode: int = 1) -> None:
        data = message if isinstance(message, bytes) else json.dumps(message).encode()
        mask, n = os.urandom(4), len(data)
        if n < 126:
            head = bytes([0x80 | opcode, 0x80 | n])
        elif n < 65536:
            head = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", n)
        else:
            head = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _receive(self) -> dict:
        chunks = bytearray()
        while True:
            first, second = self._recv(2)
            opcode, n = first & 15, second & 127
            if n == 126:
                n = struct.unpack(">H", self._recv(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv(8))[0]
            mask = self._recv(4) if second & 128 else None
            payload = self._recv(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 8:
                raise ConnectionError("Codex daemon closed the connection")
            if opcode == 9:
                self._send(payload, opcode=10)
            elif opcode in (0, 1, 2):
                chunks += payload
                if first & 128:
                    return json.loads(chunks)

    def call(self, method: str, params: dict) -> dict:
        self.calls += 1
        self._send({"id": self.calls, "method": method, "params": params})
        deadline = time.monotonic() + CALL_SECONDS
        while True:  # notifications and server requests are ignored, never answered
            if time.monotonic() > deadline:  # a chatty daemon must not stall the collector
                raise TimeoutError(f"{method}: no answer within {CALL_SECONDS:.0f}s")
            message = self._receive()
            if message.get("id") == self.calls and "method" not in message:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def loaded(self) -> dict[str, dict]:
        threads = {}
        for thread_id in self.call("thread/loaded/list", {})["data"]:
            with contextlib.suppress(RuntimeError, KeyError):  # one unreadable thread: skip it
                read = self.call("thread/read", {"threadId": thread_id, "includeTurns": False})
                threads[thread_id] = read["thread"]
        return threads

    def close(self) -> None:
        self.sock.close()


@dataclass
class Thread:
    path: str
    session_id: str = ""
    offset: int = 0
    cwd: str | None = None
    title: str | None = None
    parent: str | None = None  # evidenced thread_spawn parent
    unresolved: bool = False  # a subagent form without an established parent
    request_id: str | None = None
    request_started: float = 0.0
    activity: str | None = None
    last_ts: float = 0.0
    done: list[tuple[str, float, str]] = field(default_factory=list)  # not checkpointed


def spawn_info(source: object) -> tuple[dict, bool]:
    """(thread_spawn fields, unresolved) from a rollout or daemon `source`.

    Only `thread_spawn` establishes a parent; other subagent forms (reviewers)
    stay unresolved rather than being attached by nickname, depth or cwd.
    """
    sub = (source.get("subagent") or source.get("subAgent")) if isinstance(source, dict) else None
    if sub is None:
        return {}, False
    spawn = sub.get("thread_spawn") if isinstance(sub, dict) else None
    if isinstance(spawn, dict) and spawn.get("parent_thread_id"):
        return spawn, False
    return {}, True


_SCRIPT_CMD = re.compile(r"""["']?cmd["']?\s*:\s*(["'`])(.+?)\1""", re.S)
_SCRIPT_TOOL = re.compile(r"tools\.([A-Za-z_]+)\(")


def describe(name: str, args: object) -> str:
    if name == "exec" and isinstance(args, str):
        # The `exec` tool carries a small script calling `tools.<name>(...)`.
        if "apply_patch" in args:
            return "Editing files"
        if command := _SCRIPT_CMD.search(args):
            lines = command.group(2).replace("\\n", "\n").strip().splitlines()  # JS-escaped
            return short(f"Running {lines[0]}")
        tools = _SCRIPT_TOOL.findall(args)
        return short("Using " + tools[-1].replace("__", " ")) if tools else "Running a script"
    if name in ("exec", "exec_command", "shell", "local_shell"):
        if isinstance(args, dict):
            args = args.get("cmd") or args.get("command") or ""
        if isinstance(args, list):
            args = " ".join(map(str, args))
        first = str(args).strip().splitlines()[:1]
        return short(f"Running {first[0]}" if first else "Running a command")
    if name == "apply_patch":
        return "Editing files"
    if name == "spawn_agent":
        task = args.get("task_name") if isinstance(args, dict) else None
        return short(f"Delegating: {task}") if task else "Delegating to a helper"
    if name == "wait_agent":
        return "Waiting on a helper"
    if name == "request_user_input":
        return "Asking a question"
    return f"Using {name}"


def advance(t: Thread, r: dict) -> None:
    ts = epoch(r.get("timestamp"), t.last_ts)
    t.last_ts = max(t.last_ts, ts)
    payload = r.get("payload")
    if not isinstance(payload, dict):
        return
    kind, sub = r.get("type"), payload.get("type")
    if kind == "session_meta":
        if t.session_id:
            return  # a forked rollout repeats its parent's header; the first is its own
        t.session_id = payload.get("id") or t.session_id
        t.cwd = payload.get("cwd") or t.cwd
        spawn, t.unresolved = spawn_info(payload.get("source"))
        t.parent = spawn.get("parent_thread_id")
        t.title = spawn.get("agent_nickname") or spawn.get("agent_role") or t.title
    elif kind == "turn_context":
        t.cwd = payload.get("cwd") or t.cwd
    elif kind == "event_msg" and sub == "task_started":
        t.request_id, t.request_started, t.activity = payload.get("turn_id"), ts, None
    elif kind == "event_msg" and sub == "task_complete":
        turn, message = payload.get("turn_id") or t.request_id, payload.get("last_agent_message")
        if turn and isinstance(message, str) and message.strip():
            t.done.append((turn, float(payload.get("completed_at") or ts), message))
        t.request_id, t.activity = None, None
    elif kind == "event_msg" and sub == "turn_aborted":
        t.request_id, t.activity = None, None
    elif kind == "event_msg" and sub == "user_message" and t.title is None and not t.parent:
        t.title = short(payload.get("message") or "", 60) or None
    elif kind == "response_item" and sub in ("function_call", "custom_tool_call"):
        args = payload.get("input")
        if sub == "function_call":
            with contextlib.suppress(ValueError, TypeError):
                args = json.loads(payload.get("arguments") or "{}")
        t.activity = describe(payload.get("name") or "a tool", args)
    elif kind == "response_item" and sub == "message" and payload.get("role") == "assistant":
        t.activity = "Writing a response"


class CodexAdapter:
    harness = "codex"

    def __init__(self, home: Path, state: dict | None = None, connect=Daemon):
        self.home = home
        state = state or {}
        self.threads = {p: Thread(**v) for p, v in state.get("threads", {}).items()}
        self.hooked: dict[str, dict] = state.get("hooked", {})  # session_id -> {live, at}
        self._connect = connect
        self._daemon: Daemon | None = None
        self._tried = 0.0
        self._daemon_error: str | None = None
        self._discovered = 0.0

    def checkpoint(self) -> dict:
        threads = {p: asdict(t) | {"done": []} for p, t in self.threads.items()}
        return {"threads": threads, "hooked": self.hooked}

    def _discover(self, now: float) -> None:
        cutoff, seen = now - RETAIN_SECONDS, set()
        for path in (self.home / "sessions").glob("*/*/*/rollout-*.jsonl"):
            key = str(path)
            with contextlib.suppress(OSError):
                if path.stat().st_mtime < cutoff:
                    continue  # untouched for the whole history window: no longer tracked
                seen.add(key)
                if key not in self.threads:
                    self.threads[key] = Thread(key)
        for key in [k for k in self.threads if k not in seen]:
            del self.threads[key]

    def _loaded(self, now: float) -> dict[str, dict] | None:
        """Loaded threads by id, or None while the daemon cannot be read."""
        sock = self.home / "app-server-control/app-server-control.sock"
        if self._daemon is None:
            if now - self._tried < RECONNECT_EVERY:
                return None
            self._tried = now
            if not sock.exists():
                self._daemon_error = "Codex daemon is not running"
                return None
        try:
            if self._daemon is None:
                self._daemon = self._connect(sock)
            self._daemon_error = None
            return self._daemon.loaded()
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            self._daemon_error = f"Codex daemon status unavailable: {error}"
            with contextlib.suppress(Exception):
                if self._daemon:
                    self._daemon.close()
            self._daemon = None
            return None

    def poll(self, events: list[dict], now: float) -> Result:
        result = Result()
        if now - self._discovered >= DISCOVER_EVERY:
            self._discover(now)
            self._discovered = now
        for event in events:
            if sid := event.get("session_id"):
                name = event.get("hook_event_name")
                self.hooked[sid] = {"live": name != "SessionEnd", "at": event.get("ts_ns", 0) / 1e9}
        loaded = self._loaded(now)
        if loaded is None and self._daemon_error:
            result.gaps.append(self._daemon_error)
        loaded = loaded or {}

        poked = {e.get("transcript_path") for e in events}
        poked |= {info.get("path") for info in loaded.values()}
        for key in poked - self.threads.keys():
            if key and os.path.exists(key):
                self.threads[key] = Thread(key)
        for key, t in self.threads.items():
            size = -1
            with contextlib.suppress(OSError):
                size = os.path.getsize(key)
            if key in poked or (size != t.offset and size >= 0):
                tail = Journal(Path(key), t.offset)
                try:
                    for record in tail.records():
                        if isinstance(record, dict):
                            advance(t, record)
                except OSError as error:
                    result.gaps.append(f"{os.path.basename(key)}: {error}")
                t.offset = tail.offset

        by_id: dict[str, Thread] = {}
        for t in sorted(self.threads.values(), key=lambda t: t.last_ts):
            if not t.session_id:
                continue
            if earlier := by_id.get(t.session_id):  # a continued session spans several rollouts
                t.done[:0] = earlier.done
                earlier.done.clear()
            by_id[t.session_id] = t
        for thread_id, info in loaded.items():  # loaded but without a readable rollout yet
            if thread_id not in by_id:
                spawn, unresolved = spawn_info(info.get("source"))
                by_id[thread_id] = Thread(
                    "", thread_id, parent=spawn.get("parent_thread_id"), unresolved=unresolved,
                    title=spawn.get("agent_nickname"),
                )
        children: dict[str, list[Thread]] = {}
        for t in by_id.values():
            if t.parent:
                t.done.clear()  # helper turns are not the author's requests
                children.setdefault(t.parent, []).append(t)

        hidden = 0
        for t in by_id.values():
            if t.unresolved:
                t.done.clear()
                hidden += t.session_id in loaded
                continue
            if t.parent:
                continue
            for request_id, completed_at, response in t.done:
                result.completions.append(
                    CompletionObs(
                        harness="codex", session_id=t.session_id, request_id=request_id,
                        completed_at=completed_at, response=response, title=t.title, cwd=t.cwd,
                    )
                )
            t.done.clear()
            obs = self._observe(t, loaded.get(t.session_id), None, now)
            if obs is None:
                continue
            result.sessions.append(obs)
            self._helpers(t, obs, children, loaded, now, result)
        if hidden:
            result.gaps.append(f"{hidden} loaded helper(s) without an evidenced parent hidden")
        for sid in [s for s, h in self.hooked.items() if now - h["at"] > RETAIN_SECONDS]:
            del self.hooked[sid]
        return result

    def _helpers(self, parent: Thread, parent_obs: SessionObs, children, loaded, now, result):
        recent = [
            h for h in children.get(parent.session_id, [])
            if h.last_ts >= parent.request_started or h.session_id in loaded
        ]
        for h in sorted(recent, key=lambda h: h.last_ts)[-MAX_HELPERS:]:
            obs = self._observe(h, loaded.get(h.session_id), parent_obs, now)
            if obs:
                result.sessions.append(obs)
                self._helpers(h, obs, children, loaded, now, result)

    def _observe(self, t: Thread, info: dict | None, parent: SessionObs | None, now: float):
        info = info or {}
        status = info.get("status") or {}
        hooked = self.hooked.get(t.session_id)
        hook_live = bool(hooked and hooked["live"] and now - hooked["at"] < HOOK_LIVE_SECONDS)
        flags = status.get("activeFlags") or []
        gap, activity = None, t.activity
        if status.get("type") == "active":
            reason = next((WAIT_FLAGS[f] for f in flags if f in WAIT_FLAGS), None)
            state, activity = ("waiting", reason) if reason else ("working", t.activity)
        elif status.get("type") == "idle":
            state, activity = "idle", None
        elif status.get("type") == "systemError":
            state, activity, gap = "unknown", None, "Codex reports a system error for this thread"
        elif parent is not None:  # a helper outside the daemon lives as long as its parent
            state = "working" if t.request_id else "idle"
            gap = OUTSIDE_DAEMON if t.request_id else None
        elif hooked and not hooked["live"]:
            return None  # SessionEnd observed
        elif hook_live:
            state, gap = ("working" if t.request_id else "idle"), OUTSIDE_DAEMON
        elif t.request_id and now - t.last_ts <= HOT_SECONDS:
            state = "working" if now - t.last_ts <= UNKNOWN_AFTER else "unknown"
            gap = OUTSIDE_DAEMON
        else:
            return None  # no request and no liveness evidence: history, not activity
        if state != "working":
            activity = activity if state == "waiting" else None
        title = t.title or info.get("agentNickname") or info.get("name")
        return SessionObs(
            harness="codex", session_id=t.session_id, state=state, activity=activity,
            parent_id=parent.session_id if parent else None, cwd=t.cwd or info.get("cwd"),
            title=title or short(info.get("preview") or "", 60) or None, request_id=t.request_id,
            observed_at=max(t.last_ts, (hooked or {}).get("at", 0.0)) or now, gap=gap,
        )
