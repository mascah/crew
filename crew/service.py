"""The Mini service: durable ingest, the page's read API, and the built UI.

Roles are explicit. Viewers are the configured Tailscale account, identified
by the header Tailscale Serve sets; collectors present a per-machine upload
token that grants reporting and nothing else. Loopback alone grants neither.
"""

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from crew import config
from crew.model import (
    AdapterStatus,
    CompletionDetail,
    CompletionPage,
    CompletionSummary,
    MachineView,
    ProjectRef,
    ProjectView,
    Report,
    ReportAck,
    SessionView,
    Snapshot,
)

EXCERPT = 240
MAX_UPLOAD = 64 * 1024 * 1024  # one report carries at most a batch of final responses
SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, last_seen REAL NOT NULL, report TEXT NOT NULL,
    expired INTEGER NOT NULL DEFAULT 0, expired_at REAL NOT NULL DEFAULT 0,
    expired_seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_keys (
    key TEXT PRIMARY KEY, project_id TEXT NOT NULL, explicit INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, machine_id TEXT NOT NULL, harness TEXT NOT NULL,
    session_id TEXT NOT NULL, request_id TEXT NOT NULL, completed_at REAL NOT NULL,
    project_id TEXT, title TEXT, response TEXT NOT NULL,
    UNIQUE (machine_id, harness, session_id, request_id));
CREATE INDEX IF NOT EXISTS completions_time ON completions (completed_at);
"""


class Store:
    def __init__(self, path: Path, cfg: config.Config):
        self.path, self.cfg = path, cfg
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        # One short-lived connection per call; rollback journal with FULL sync.
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute("PRAGMA synchronous = FULL")
        return db

    # --- project identity ---

    def _resolve(self, db: sqlite3.Connection, ref: ProjectRef | None) -> str | None:
        """Persisted project ID: explicit mapping, then cached local key, then origin."""
        if ref is None or not ref.keys:
            return None
        marks = ",".join("?" * len(ref.keys))
        rows = db.execute(
            f"SELECT key, project_id, explicit FROM project_keys WHERE key IN ({marks})",  # noqa: S608
            ref.keys,
        ).fetchall()
        known = {key: project_id for key, project_id, _ in rows}
        explicit = [project_id for _, project_id, flag in rows if flag]
        if explicit:
            project_id = explicit[0]
        elif ref.keys[0] in known:
            return known[ref.keys[0]]  # a changed remote never rewrites this checkout
        elif known:
            project_id = next(known[k] for k in ref.keys if k in known)
        else:
            project_id = uuid.uuid4().hex[:12]
            # Without an origin the same path on the other Mac is another project.
            local = f"{ref.checkout} on {ref.keys[0].split(':', 2)[1]}"
            detail = next((k[7:] for k in ref.keys if k.startswith("origin:")), local)
            db.execute("INSERT INTO projects VALUES (?, ?, ?)", (project_id, ref.name, detail))
        db.executemany(
            "INSERT OR IGNORE INTO project_keys (key, project_id) VALUES (?, ?)",
            [(key, project_id) for key in ref.keys],
        )
        return project_id

    def map_key(self, key: str, project_id: str) -> None:
        """Explicit mapping: takes precedence over automatic discovery."""
        with self._db() as db:
            if not db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
                raise KeyError(project_id)
            db.execute("INSERT OR REPLACE INTO project_keys VALUES (?, ?, 1)", (key, project_id))

    def projects(self) -> list[tuple[ProjectView, list[str]]]:
        with self._db() as db:
            keys: dict[str, list[str]] = {}
            for key, project_id, explicit in db.execute("SELECT * FROM project_keys ORDER BY key"):
                keys.setdefault(project_id, []).append(key + (" (explicit)" if explicit else ""))
            rows = db.execute("SELECT id, name, detail FROM projects ORDER BY name, id").fetchall()
        return [(ProjectView(id=i, name=n, detail=d), keys.get(i, [])) for i, n, d in rows]

    # --- ingest ---

    def ingest(self, report: Report, now: float) -> int:
        """Commit one report durably; the caller acknowledges only after this returns."""
        db = self._db()
        try:
            db.execute("BEGIN IMMEDIATE")
            sessions = []
            for s in report.sessions:
                project_id = self._resolve(db, s.project)
                checkout = s.project.checkout if s.project else s.cwd
                sessions.append(s.model_dump(exclude={"project"})
                                | {"project_id": project_id, "checkout": checkout})
            stored = {"sessions": sessions, "adapters": [a.model_dump() for a in report.adapters]}
            db.execute(
                "INSERT INTO machines (id, name, last_seen, report) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET name = excluded.name,"
                " last_seen = excluded.last_seen, report = excluded.report",
                (report.machine_id, report.machine_name, now, json.dumps(stored)),
            )
            seen, expired, expired_at = db.execute(
                "SELECT expired_seen, expired, expired_at FROM machines WHERE id = ?",
                (report.machine_id,)).fetchone()
            total = report.expired_total
            lost = total - seen if total >= seen else total  # a rebuilt queue counts from zero
            if lost:  # losses older than the history window no longer explain a missing entry
                window = self.cfg.retention_days * 86400
                expired, expired_at = lost + (expired if now - expired_at < window else 0), now
            db.execute(
                "UPDATE machines SET expired_seen = ?, expired = ?, expired_at = ? WHERE id = ?",
                (total, expired, expired_at, report.machine_id))
            for c in report.completions:
                # Replay is a no-op; a later settlement of the same request supersedes.
                db.execute(
                    "INSERT INTO completions (machine_id, harness, session_id, request_id,"
                    " completed_at, project_id, title, response) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (machine_id, harness, session_id, request_id) DO UPDATE SET"
                    " completed_at = excluded.completed_at, response = excluded.response,"
                    " title = excluded.title, project_id = excluded.project_id"
                    " WHERE excluded.completed_at > completions.completed_at",
                    (report.machine_id, c.harness, c.session_id, c.request_id, c.completed_at,
                     self._resolve(db, c.project), c.title, c.response),
                )
            self._expire(db, now)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()
        return len(report.completions)

    def _expire(self, db: sqlite3.Connection, now: float) -> None:
        """By completion time, never upload time: seven days or the entry cap."""
        db.execute("DELETE FROM completions WHERE completed_at < ?",
                   (now - self.cfg.retention_days * 86400,))
        db.execute(
            "DELETE FROM completions WHERE id NOT IN (SELECT id FROM completions"
            " ORDER BY completed_at DESC, id DESC LIMIT ?)", (self.cfg.completion_cap,),
        )

    # --- reads ---

    def snapshot(self, now: float) -> Snapshot:
        with self._db() as db:
            machines = db.execute("SELECT * FROM machines ORDER BY name, id").fetchall()
            projects = db.execute("SELECT id, name, detail FROM projects ORDER BY name").fetchall()
            used = {i for (i,) in db.execute("SELECT DISTINCT project_id FROM completions")}
        views, sessions = [], []
        expiry_window = self.cfg.retention_days * 86400
        for machine_id, name, last_seen, report, expired, expired_at, _ in machines:
            stored = json.loads(report)
            views.append(MachineView(
                id=machine_id, name=name, last_seen=last_seen,
                stale=now - last_seen > self.cfg.stale_seconds,
                adapters=[AdapterStatus(**a) for a in stored["adapters"]],
                expired_pending=expired if now - expired_at < expiry_window else 0,
            ))
            sessions += self._tree(machine_id, stored["sessions"])
            used |= {s.get("project_id") for s in stored["sessions"]}
        return Snapshot(
            server_time=now, stale_after=self.cfg.stale_seconds, machines=views, sessions=sessions,
            # Identity rows are kept for good; the page only needs the ones in view.
            projects=[ProjectView(id=i, name=n, detail=d) for i, n, d in projects if i in used],
        )

    @staticmethod
    def _tree(machine_id: str, stored: list[dict]) -> list[SessionView]:
        """Helpers nest beneath their evidenced parent; they are never top-level."""
        views, parents = {}, {}
        for s in stored:
            key = (s["harness"], s["session_id"])
            parents[key] = (s["harness"], s["parent_id"]) if s.get("parent_id") else None
            views[key] = SessionView(
                key=f"{machine_id}/{s['harness']}/{s['session_id']}", machine_id=machine_id,
                **{k: s.get(k) for k in ("harness", "session_id", "state", "activity", "title",
                                         "project_id", "checkout", "observed_at", "gap")},
            )
        for key, parent in parents.items():
            if parent in views:
                views[parent].helpers.append(views[key])
        return [views[key] for key, parent in parents.items() if parent is None]

    def completions(self, now: float, limit: int, offset: int) -> CompletionPage:
        with self._db() as db:
            self._expire(db, now)
            total = db.execute("SELECT COUNT(*) FROM completions").fetchone()[0]
            rows = db.execute(
                "SELECT id, machine_id, harness, session_id, project_id, title, completed_at,"
                " substr(response, 1, ?) FROM completions"
                " ORDER BY completed_at DESC, id DESC LIMIT ? OFFSET ?",
                (EXCERPT, limit, offset),
            ).fetchall()
        fields = ("id", "machine_id", "harness", "session_id", "project_id", "title",
                  "completed_at", "excerpt")
        items = [CompletionSummary(**dict(zip(fields, row, strict=True))) for row in rows]
        return CompletionPage(items=items, total=total)

    def completion(self, completion_id: int) -> CompletionDetail | None:
        with self._db() as db:
            row = db.execute(
                "SELECT id, machine_id, harness, session_id, project_id, title, completed_at,"
                " response FROM completions WHERE id = ?", (completion_id,),
            ).fetchone()
        if row is None:
            return None
        fields = ("id", "machine_id", "harness", "session_id", "project_id", "title",
                  "completed_at", "response")
        detail = dict(zip(fields, row, strict=True))
        return CompletionDetail(**detail, excerpt=detail["response"][:EXCERPT])


def create_app(cfg: config.Config, store: Store, now: Callable[[], float] = time.time,
               ui: Path | None = None) -> FastAPI:
    app = FastAPI(title="Crew", version="0.1.0", docs_url=None, redoc_url=None)
    viewers = {login.lower() for login in cfg.viewer_logins}

    def viewer(request: Request) -> None:
        login = request.headers.get("tailscale-user-login", "").lower()
        if not login or login not in viewers:  # a missing identity is never a viewer
            raise HTTPException(403, "This page is limited to the configured Tailscale account")

    def collector(request: Request) -> str:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        machine = cfg.collectors.get(hashlib.sha256(token.encode()).hexdigest())
        if scheme.lower() != "bearer" or not token or machine is None:
            raise HTTPException(401, "Unknown collector credential")
        return machine

    @app.middleware("http")
    async def uploads(request: Request, call_next):
        # Before any body is read: only a known collector may upload, within a bound.
        if request.method == "POST":
            try:
                collector(request)
            except HTTPException as refused:
                return JSONResponse({"detail": refused.detail}, refused.status_code)
            if int(request.headers.get("content-length") or 0) > MAX_UPLOAD:
                return JSONResponse({"detail": "Report too large"}, 413)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/ingest")
    def ingest(report: Report, machine: str = Depends(collector)) -> ReportAck:
        if report.machine_id != machine:
            raise HTTPException(403, "This credential reports for a different machine")
        return ReportAck(accepted=store.ingest(report, now()))

    @app.get("/api/snapshot", dependencies=[Depends(viewer)])
    def snapshot() -> Snapshot:
        return store.snapshot(now())

    @app.get("/api/completions", dependencies=[Depends(viewer)])
    def completions(limit: int = 20, offset: int = 0) -> CompletionPage:
        return store.completions(now(), max(1, min(limit, 100)), max(0, offset))

    @app.get("/api/completions/{completion_id}", dependencies=[Depends(viewer)])
    def completion(completion_id: int) -> CompletionDetail:
        detail = store.completion(completion_id)
        if detail is None:
            raise HTTPException(404, "This finished request is no longer retained")
        return detail

    if ui and ui.is_dir():
        app.mount("/", StaticFiles(directory=ui, html=True), name="ui")
    return app
