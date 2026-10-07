"""Crew observer for Hermes Agent: in-process callbacks, local appends only.

Self-contained on purpose: it runs inside Hermes's own Python environment.
Every observer returns None, so prompts, approvals and continuation stay with
Hermes; a failed write is recorded beside the journal and never raised.
"""

import contextlib
import fcntl
import json
import os
import time
from pathlib import Path

HOME = Path(os.environ.get("CREW_HOME", "~/Library/Application Support/Crew")).expanduser()
JOURNAL = HOME / "journal.jsonl"
EVENTS = (
    "on_session_start", "pre_llm_call", "post_llm_call", "pre_tool_call", "on_session_end",
    "on_session_finalize", "on_session_reset", "on_human_input_request",
    "on_human_input_resolved", "subagent_start", "subagent_stop",
)
FIELDS = (
    "session_id", "turn_id", "completed", "failed", "interrupted", "turn_exit_reason",
    "platform", "tool_name", "kind", "request_id", "outcome", "parent_session_id",
    "child_session_id", "child_role", "child_status", "old_session_id", "new_session_id",
)


def _append(path: Path, entry: dict) -> None:
    line = (json.dumps(entry, default=str) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        for attempt in range(6):  # shared lock: only a truncation makes us wait
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if attempt == 5:
                    raise
                time.sleep(0.001)
        os.write(fd, line)
    finally:
        os.close(fd)


def _emit(event: str, **fields) -> None:
    try:
        entry = {"ts_ns": time.time_ns(), "harness": "hermes", "event": event,
                 "pid": os.getpid(), "hermes_home": os.environ.get("HERMES_HOME", ""), **fields}
        with contextlib.suppress(OSError):  # the working folder may have been removed
            entry["cwd"] = os.getcwd()
        _append(JOURNAL, entry)
    except Exception:  # observation must never disturb the agent
        with contextlib.suppress(Exception):
            _append(JOURNAL.with_name(JOURNAL.name + ".errors"),
                    {"ts_ns": time.time_ns(), "harness": "hermes"})


def register(ctx) -> None:
    from hermes_cli.plugins import VALID_HOOKS

    available = [event for event in EVENTS if event in VALID_HOOKS]
    for event in available:
        def observe(_event=event, **kwargs):
            fields = {k: kwargs[k] for k in FIELDS if kwargs.get(k) is not None}
            if _event == "post_llm_call" and kwargs.get("assistant_response") is not None:
                fields["response"] = str(kwargs["assistant_response"])
            _emit(_event, **fields)

        ctx.register_hook(event, observe)
    _emit("plugin_loaded", hooks=available)
