"""Shared observation shapes: what collectors report and what the page reads.

Request outcome (a completion), session state, and reporter freshness are
separate facts and stay in separate fields.
"""

from typing import Literal

from pydantic import BaseModel, field_validator

Harness = Literal["claude", "codex", "hermes"]
# "unknown" is an explicit observation gap, never a guess at idle.
State = Literal["working", "waiting", "idle", "unknown"]


class ProjectRef(BaseModel):
    # Identity candidates, machine-local key first; the service resolves them
    # to a persisted Crew project ID (see crew/project.py).
    keys: list[str]
    name: str
    checkout: str


class Observed(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _well_formed(cls, value: object) -> object:
        # A record cut mid-character leaves a lone surrogate that cannot be stored or sent.
        return value.encode("utf-8", "replace").decode() if isinstance(value, str) else value


class SessionObs(Observed):
    harness: Harness
    session_id: str
    parent_id: str | None = None  # evidenced native parent; never inferred
    state: State
    activity: str | None = None
    title: str | None = None
    cwd: str | None = None
    project: ProjectRef | None = None
    request_id: str | None = None
    observed_at: float  # time of the latest native evidence (epoch seconds)
    gap: str | None = None  # what could not be observed for this session


class CompletionObs(Observed):
    """A settled response cycle with its delivered final response."""

    harness: Harness
    session_id: str
    request_id: str
    completed_at: float
    response: str
    title: str | None = None
    cwd: str | None = None
    project: ProjectRef | None = None


class AdapterStatus(BaseModel):
    harness: Harness
    ok: bool
    error: str | None = None
    gaps: list[str] = []


class Report(BaseModel):
    """One collector upload: a full current snapshot plus queued completions."""

    machine_id: str
    machine_name: str
    sent_at: float
    sessions: list[SessionObs]
    adapters: list[AdapterStatus]
    completions: list[CompletionObs] = []
    # Running total dropped by this collector's outage-queue limits. A total,
    # not a delta, so a replayed report cannot count the same loss twice.
    expired_total: int = 0


class ReportAck(BaseModel):
    accepted: int


# --- what the page reads ---


class SessionView(BaseModel):
    key: str  # machine/harness/session_id: stable through resume
    machine_id: str
    harness: Harness
    session_id: str
    state: State
    activity: str | None
    title: str | None
    project_id: str | None
    checkout: str | None
    observed_at: float
    gap: str | None
    helpers: list["SessionView"] = []


class MachineView(BaseModel):
    id: str
    name: str
    last_seen: float  # service receipt time
    stale: bool
    adapters: list[AdapterStatus]
    expired_pending: int  # finished requests lost to this Mac's outage-queue limits


class ProjectView(BaseModel):
    id: str
    name: str
    detail: str  # distinguishes same-named projects (origin or folder)


class Snapshot(BaseModel):
    server_time: float
    stale_after: float
    machines: list[MachineView]
    projects: list[ProjectView]
    sessions: list[SessionView]


class CompletionSummary(BaseModel):
    id: int
    machine_id: str
    harness: Harness
    session_id: str
    project_id: str | None
    title: str | None
    completed_at: float
    excerpt: str


class CompletionDetail(CompletionSummary):
    response: str


class CompletionPage(BaseModel):
    items: list[CompletionSummary]
    total: int  # retained entries; page with ?offset=
