"""Harness adapters: native evidence in, common observations out.

An adapter is polled with the new journal events for its harness and returns
its current sessions plus newly settled completions. `state` round-trips
through JSON so the collector can checkpoint it with the outbox.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from crew.model import CompletionObs, SessionObs

RETAIN_SECONDS = 7 * 86400  # native records older than this are not backfilled


@dataclass
class Result:
    sessions: list[SessionObs] = field(default_factory=list)
    completions: list[CompletionObs] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


class Adapter(Protocol):
    harness: str

    def poll(self, events: list[dict], now: float) -> Result: ...
    def checkpoint(self) -> dict: ...


def epoch(iso: str | None, default: float = 0.0) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        return default


def short(text: object, limit: int = 80) -> str:
    line = " ".join(str(text).split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def pid_alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)  # type: ignore[call-overload]
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False
    return True
