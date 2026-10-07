"""The per-Mac collector: poll adapters, queue completions durably, report.

Agent callbacks only append to the local journal; every read of native
records and all networking happen here. Current state is sent as a fresh
snapshot and never queued, so replay after an outage cannot make old work
look current. Completions wait in a SQLite outbox until the service has
acknowledged a durable commit.
"""

import hashlib
import json
import logging
import sqlite3
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from crew import config
from crew.adapters import Adapter
from crew.adapters.claude import ClaudeAdapter
from crew.adapters.codex import CodexAdapter
from crew.adapters.hermes import HermesAdapter
from crew.journal import Journal
from crew.model import AdapterStatus, CompletionObs, Report, ReportAck
from crew.project import identify_cached

log = logging.getLogger("crew.collector")
BATCH = 50
CHECKPOINT_EVERY = 30.0
MAX_BACKOFF = 30.0  # no longer than the stale threshold: a restarted service sees us within it


class Outbox:
    def __init__(self, path: Path, cfg: config.Config):
        self.cfg = cfg
        # Rollback journal with FULL sync: durable without depending on a WAL fix.
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA synchronous = FULL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS completions (
                id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL,
                completed_at REAL NOT NULL, bytes INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )

    def _meta(self, key: str, default: str) -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def checkpoint(self) -> dict:
        return json.loads(self._meta("checkpoint", "{}"))

    @property
    def expired(self) -> int:
        """Completions ever dropped by the queue limits; reported as a running total."""
        return int(self._meta("expired", "0"))

    def commit(self, completions: list[CompletionObs], checkpoint: dict, now: float) -> None:
        """Queue completions together with the source checkpoint that covers them."""
        put = "INSERT OR REPLACE INTO meta VALUES (?, ?)"
        horizon = now - self.cfg.queue_days * 86400
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for c in completions:
                if c.completed_at < horizon:
                    continue  # backfill older than retention was never pending: not a loss
                payload = c.model_dump_json()
                self.db.execute(
                    # Replay is a no-op; a later settlement of the same request supersedes.
                    "INSERT INTO completions (key, completed_at, bytes, payload)"
                    " VALUES (?, ?, ?, ?) ON CONFLICT (key) DO UPDATE SET"
                    " completed_at = excluded.completed_at, bytes = excluded.bytes,"
                    " payload = excluded.payload"
                    " WHERE excluded.completed_at > completions.completed_at",
                    (f"{c.harness}/{c.session_id}/{c.request_id}", c.completed_at,
                     len(payload.encode()), payload),
                )
            self.db.execute(put, ("checkpoint", json.dumps(checkpoint)))
            dropped = self._enforce_limits(now)
            if dropped:
                self.db.execute(put, ("expired", str(self.expired + dropped)))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _enforce_limits(self, now: float) -> int:
        """Expire the oldest pending completions past the age, count or byte bound."""
        cfg = self.cfg
        dropped = self.db.execute(
            "DELETE FROM completions WHERE completed_at < ?", (now - cfg.queue_days * 86400,)
        ).rowcount
        dropped += self.db.execute(
            "DELETE FROM completions WHERE id NOT IN"
            " (SELECT id FROM completions ORDER BY completed_at DESC, id DESC LIMIT ?)",
            (cfg.queue_completions,),
        ).rowcount
        total = self.db.execute("SELECT COALESCE(SUM(bytes), 0) FROM completions").fetchone()[0]
        for row_id, size in self.db.execute(
            "SELECT id, bytes FROM completions ORDER BY completed_at, id"
        ).fetchall():
            if total <= cfg.queue_bytes:
                break
            self.db.execute("DELETE FROM completions WHERE id = ?", (row_id,))
            total -= size
            dropped += 1
        return dropped

    def pending(self, limit: int = BATCH) -> list[tuple[int, CompletionObs]]:
        rows = self.db.execute(
            "SELECT id, payload FROM completions ORDER BY completed_at, id LIMIT ?", (limit,)
        ).fetchall()
        return [(row_id, CompletionObs.model_validate_json(payload)) for row_id, payload in rows]

    def acknowledge(self, sent: list[tuple[int, CompletionObs]]) -> None:
        """Called only after the service confirmed its durable commit."""
        self.db.execute("BEGIN IMMEDIATE")
        # Only what was sent: a later settlement queued meanwhile stays pending.
        self.db.executemany("DELETE FROM completions WHERE id = ? AND completed_at = ?",
                            [(row_id, c.completed_at) for row_id, c in sent])
        self.db.execute("COMMIT")


def http_upload(cfg: config.Config) -> Callable[[Report], ReportAck]:
    # ponytail: a new connection per report (a TLS handshake from the MacBook, about
    # 1.5% of a core while a session changes every poll); keep one open if that matters.
    def upload(report: Report) -> ReportAck:
        request = urllib.request.Request(
            cfg.service_url.rstrip("/") + "/api/ingest",
            data=report.model_dump_json().encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg.token}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return ReportAck.model_validate_json(response.read())

    return upload


class Collector:
    def __init__(self, cfg: config.Config, home: Path, upload: Callable[[Report], ReportAck],
                 adapters: list[Adapter] | None = None):
        home.mkdir(parents=True, exist_ok=True)
        self.cfg, self.upload = cfg, upload
        self.outbox = Outbox(home / "collector.db", cfg)
        self.saved = self.outbox.checkpoint()  # the last durably committed checkpoint
        self.journal = Journal(home / "journal.jsonl", self.saved.get("journal", 0))
        self.build: dict[str, Callable[[dict | None], Adapter]] = {} if adapters else {
            "claude": lambda state: ClaudeAdapter(Path(cfg.claude_home).expanduser(), state),
            "codex": lambda state: CodexAdapter(Path(cfg.codex_home).expanduser(), state),
            "hermes": lambda state: HermesAdapter(Path(cfg.hermes_home).expanduser(), state),
        }
        self.adapters = adapters or [
            make(self.saved.get(harness)) for harness, make in self.build.items()]
        self.failing: dict[str, str] = {}  # harness -> error, while its poll keeps raising
        self.callback_errors: dict[str, int] = {}
        self._sent_at = self._saved_at = self._retry_at = 0.0
        self._sent = ""
        self._failures = 0

    def _project(self, cwd: str | None):
        return identify_cached(self.cfg.machine_id, cwd) if cwd else None

    def tick(self, now: float) -> None:
        events = self.journal.read()
        for harness, count in self.journal.take_errors().items():
            self.callback_errors[harness] = self.callback_errors.get(harness, 0) + count
        sessions, completions, statuses = [], [], []
        failing: dict[str, str] = {}
        for index, adapter in enumerate(self.adapters):
            harness = adapter.harness
            if harness in self.failing:  # restarted from the saved checkpoint: replay from there
                events_for = Journal(self.journal.path, self.saved.get("journal", 0)).read()
            else:
                events_for = events
            mine = [e for e in events_for if e.get("harness") == harness]
            gaps = []
            if lost := self.callback_errors.get(harness):
                gaps.append(f"{lost} callback event(s) could not be written locally")
            try:  # one adapter's failure leaves the others reporting
                result = adapter.poll(mine, now)
            except Exception as error:
                failing[harness] = f"{type(error).__name__}: {error}"
                if self.failing.get(harness) != failing[harness]:  # once, not every poll
                    log.exception("%s adapter failed", harness)
                statuses.append(AdapterStatus(
                    harness=harness, ok=False, gaps=gaps, error=failing[harness],  # type: ignore[arg-type]
                ))
                # Its half-advanced state must never be saved: start it again from
                # the last committed checkpoint so nothing it read is skipped.
                if harness in self.build:
                    self.adapters[index] = self.build[harness](self.saved.get(harness))
                continue
            sessions += result.sessions
            completions += result.completions
            statuses.append(AdapterStatus(
                harness=adapter.harness, ok=True, gaps=gaps + result.gaps,  # type: ignore[arg-type]
            ))
        for item in [*sessions, *completions]:
            item.project = self._project(item.cwd)
        sessions.sort(key=lambda s: (s.harness, s.session_id))

        self.failing = failing
        if completions or now - self._saved_at >= CHECKPOINT_EVERY:
            # A failing adapter keeps its saved checkpoint, and the journal offset
            # waits for it; the others replay those events harmlessly on restart.
            checkpoint = self.saved | {
                a.harness: a.checkpoint() for a in self.adapters if a.harness not in failing}
            if not failing:
                checkpoint["journal"] = self.journal.offset
            self.outbox.commit(completions, checkpoint, now)
            self.saved, self._saved_at = checkpoint, now
            consumed = self.journal.offset
            if not failing:
                self.journal.compact()
            if self.journal.offset != consumed:  # emptied: the saved offset must follow
                self.saved = checkpoint | {"journal": 0}
                self.outbox.commit([], self.saved, now)
        self._report(sessions, statuses, now)

    def _report(self, sessions, statuses, now: float) -> None:
        if now < self._retry_at:
            return
        pending = self.outbox.pending()
        snapshot = json.dumps(
            [[s.model_dump(exclude={"observed_at"}) for s in sessions],
             [s.model_dump() for s in statuses]], sort_keys=True,
        )
        due = now - self._sent_at >= self.cfg.heartbeat_seconds
        if not (pending or due or snapshot != self._sent):
            return
        report = Report(
            machine_id=self.cfg.machine_id, machine_name=self.cfg.machine_name, sent_at=now,
            sessions=sessions, adapters=statuses, completions=[c for _, c in pending],
            expired_total=self.outbox.expired,
        )
        try:
            self.upload(report)
        except (OSError, ValueError, urllib.error.URLError) as error:
            self._failures += 1
            self._retry_at = now + min(MAX_BACKOFF, 2.0 ** min(self._failures, 10))
            log.warning("report failed (%s); retrying in %.0fs", error, self._retry_at - now)
            return
        self._failures, self._sent_at, self._sent = 0, now, snapshot
        self.outbox.acknowledge(pending)


def run(cfg: config.Config | None = None, home: Path | None = None,
        standby: bool = False) -> None:
    cfg, home = cfg or config.load(), home or config.home()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock = config.own("collector", standby, home)  # noqa: F841 - held for the process lifetime
    collector = Collector(cfg, home, http_upload(cfg))
    log.info("collector %s reporting to %s", cfg.machine_id, cfg.service_url)
    while True:
        started = time.monotonic()
        # A failed tick exits: launchd restarts us and the checkpoint replays safely.
        collector.tick(time.time())
        time.sleep(max(0.2, cfg.poll_seconds - (time.monotonic() - started)))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
