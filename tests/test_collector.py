import subprocess
import threading

import pytest
from conftest import T0, VIEWER, completion, session
from test_claude import SID
from test_claude import Home as ClaudeHome

from crew import collector as collector_module
from crew import config, journal
from crew.adapters import Result
from crew.collector import Collector, Outbox, run
from crew.model import Report, ReportAck


class FakeAdapter:
    def __init__(self, harness="claude", state=None):
        self.harness, self.state = harness, state or {"polls": 0}
        self.sessions, self.completions, self.fail, self.events = [], [], False, []

    def poll(self, events, now):
        if self.fail:
            raise RuntimeError("transcript parser exploded")
        self.events += events
        self.state["polls"] += 1
        done, self.completions = self.completions, []
        return Result(sessions=list(self.sessions), completions=done)

    def checkpoint(self):
        return dict(self.state)


class Link:
    """The collector's upload path into the real service, with a cuttable wire."""

    def __init__(self, service):
        self.service, self.down, self.lose_ack, self.reports = service, False, False, []

    def __call__(self, report: Report) -> ReportAck:
        if self.down:
            raise ConnectionRefusedError("service unreachable")
        headers = {"Authorization": f"Bearer {report.machine_id}-token",
                   "Content-Type": "application/json"}
        response = self.service.client.post(
            "/api/ingest", content=report.model_dump_json(), headers=headers)
        assert response.status_code == 200, response.text
        self.reports.append(report)
        if self.lose_ack:
            raise TimeoutError("acknowledgment lost")
        return ReportAck(**response.json())


@pytest.fixture
def link(service):
    return Link(service)


def make(tmp_path, link, adapters, **settings):
    cfg = config.Config(machine_id="mini", machine_name="Mini", **settings)
    return Collector(cfg, tmp_path / "crew", link, adapters)


def test_outage_queues_completions_and_delivers_each_once(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    adapter.sessions = [session(cwd=None)]
    collector.tick(T0)
    assert service.snapshot()["sessions"][0]["state"] == "working"

    link.down = True
    adapter.completions = [completion("r1"), completion("r2", at=T0 + 1)]
    collector.tick(T0 + 2)
    adapter.sessions = []
    collector.tick(T0 + 3)  # still polling while the service is away
    assert adapter.state["polls"] == 3 and service.completions()["total"] == 0

    restarted = make(tmp_path, link, [FakeAdapter()])  # the queue survives a collector restart
    assert len(restarted.outbox.pending()) == 2
    link.down = False
    restarted.tick(T0 + 600)
    page = service.completions()
    assert page["total"] == 2 and page["items"][0]["completed_at"] == T0 + 1  # original times
    assert service.snapshot()["sessions"] == []  # a fresh snapshot, not replayed old work
    assert restarted.outbox.pending() == []


def test_failed_reports_back_off_without_stopping_collection(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    link.down = True
    for second in range(10):
        collector.tick(T0 + second)
    assert adapter.state["polls"] == 10
    link.down = False
    collector.tick(T0 + 10)
    assert link.reports == []  # still inside the retry delay
    collector.tick(T0 + 120)
    assert len(link.reports) == 1


def test_lost_acknowledgment_replays_without_duplicates(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    adapter.completions = [completion("r1")]
    link.lose_ack = True
    collector.tick(T0)
    assert service.completions()["total"] == 1 and len(collector.outbox.pending()) == 1
    link.lose_ack = False
    collector.tick(T0 + 120)
    assert service.completions()["total"] == 1 and collector.outbox.pending() == []
    assert len(link.reports) == 2


def test_checkpoint_commits_with_the_completions_it_covers(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    journal.append(tmp_path / "crew/journal.jsonl", {"harness": "claude", "session_id": "s"})
    journal.append(tmp_path / "crew/journal.jsonl", {"harness": "codex", "session_id": "other"})
    adapter.completions = [completion("r1")]
    collector.tick(T0)
    assert [e["session_id"] for e in adapter.events] == ["s"]  # only its own harness

    saved = Outbox(tmp_path / "crew/collector.db", collector.cfg).checkpoint()
    assert saved["claude"] == {"polls": 1} and saved["journal"] == collector.journal.offset > 0
    again = make(tmp_path, link, [FakeAdapter()])
    again.tick(T0 + 1)
    assert again.journal.offset == saved["journal"]  # consumed events are not replayed


@pytest.mark.parametrize(
    ("settings", "kept"),
    [({"queue_completions": 3}, ["r3", "r4", "r5"]),
     ({"queue_bytes": 700}, ["r4", "r5"]),
     ({"queue_days": 1.0}, ["r5"])],
)
def test_queue_limits_expire_oldest_and_expose_the_gap(tmp_path, service, link, settings, kept):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter], **settings)
    link.down = True
    ages = [5 * 86400, 4 * 86400, 3 * 86400, 2 * 86400, 86400 + 60, 0]
    adapter.completions = [
        completion(f"r{i}", at=T0 - age, response="x" * 200) for i, age in enumerate(ages)
    ]
    collector.tick(T0 - 6 * 86400)  # queued while every one of them was still fresh
    collector.tick(T0)
    assert [c.request_id for _, c in collector.outbox.pending()] == kept
    assert collector.outbox.expired == 6 - len(kept)

    link.down = False
    collector.tick(T0 + 120)
    assert service.completions()["total"] == len(kept)  # retained responses stay complete
    link.lose_ack = True  # the report lands, its acknowledgment does not, and it is replayed
    collector.tick(T0 + 240)
    link.lose_ack = False
    collector.tick(T0 + 360)
    assert service.snapshot()["machines"][0]["expired_pending"] == 6 - len(kept)  # not recounted


def test_a_later_settlement_replaces_the_queued_one(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    link.down = True
    adapter.completions = [completion("r1", response="FIRST")]
    collector.tick(T0)
    adapter.completions = [completion("r1", at=T0 + 5, response="SETTLED")]
    collector.tick(T0 + 6)
    link.down = False
    collector.tick(T0 + 120)
    [item] = service.completions()["items"]
    assert item["excerpt"] == "SETTLED"


def test_a_failed_poll_is_retried_from_the_saved_checkpoint(tmp_path, service, monkeypatch):
    """Real Claude adapter: records it read before failing are not skipped."""
    monkeypatch.setattr(collector_module, "CodexAdapter", lambda *a, **k: FakeAdapter("codex"))
    monkeypatch.setattr(collector_module, "HermesAdapter", lambda *a, **k: FakeAdapter("hermes"))
    home = ClaudeHome(tmp_path / "claude")
    cfg = config.Config(machine_id="mini", machine_name="Mini", claude_home=str(home.root))
    state = tmp_path / "state"
    collector = Collector(cfg, state, Link(service))
    home.registry("busy")
    home.prompt()
    collector.tick(home.clock)

    home.say("All green.")
    home.system("turn_duration")
    stopped = home.event("Stop")
    journal.append(state / "journal.jsonl", stopped)
    broken = collector.adapters[0]
    monkeypatch.setattr(broken, "_registry", lambda: 1 / 0)  # fails after reading the transcript
    service.now = home.clock + 40
    collector.tick(home.clock + 40)  # a checkpoint is due while the adapter is failing
    assert not service.snapshot()["machines"][0]["adapters"][0]["ok"]
    assert collector.adapters[0] is not broken and service.completions()["total"] == 0

    restarted = Collector(cfg, state, Link(service))  # even across a collector restart
    seen = []
    poll = restarted.adapters[0].poll
    monkeypatch.setattr(restarted.adapters[0], "poll",
                        lambda events, now: seen.extend(events) or poll(events, now))
    restarted.tick(home.clock + 42)
    assert [item["excerpt"] for item in service.completions()["items"]] == ["All green."]
    assert [e["hook_event_name"] for e in seen] == ["Stop"]  # its journal events came back too


def test_backfill_older_than_retention_is_not_reported_as_lost(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    adapter.completions = [completion("ancient", at=T0 - 30 * 86400), completion("recent")]
    collector.tick(T0)
    assert service.completions()["total"] == 1
    assert service.snapshot()["machines"][0]["expired_pending"] == 0


def test_one_failing_adapter_leaves_the_others_reporting(tmp_path, service, link):
    claude, codex = FakeAdapter("claude"), FakeAdapter("codex")
    claude.fail = True
    codex.sessions = [session("c1", harness="codex", state="idle")]
    collector = make(tmp_path, link, [claude, codex])
    home = tmp_path / "crew"
    (home / "journal.jsonl.errors").write_text('{"harness":"codex"}\n{"harness":"codex"}\n')
    collector.tick(T0)
    snapshot = service.snapshot()
    assert [s["session_id"] for s in snapshot["sessions"]] == ["c1"]
    adapters = {a["harness"]: a for a in snapshot["machines"][0]["adapters"]}
    assert not adapters["claude"]["ok"] and "exploded" in adapters["claude"]["error"]
    assert adapters["codex"]["ok"]
    assert adapters["codex"]["gaps"] == ["2 callback event(s) could not be written locally"]


def test_heartbeat_keeps_an_unchanged_machine_fresh(tmp_path, service, link):
    collector = make(tmp_path, link, [FakeAdapter()])
    for second in range(0, 31, 2):
        collector.tick(T0 + second)
        service.now = T0 + second
    assert len(link.reports) == 4  # first tick, then every ten seconds
    assert not service.snapshot()["machines"][0]["stale"]
    service.now += 31  # the collector stops (sleep, crash, network)
    assert service.snapshot()["machines"][0]["stale"]


def test_only_one_collector_owns_a_machine(tmp_path):
    owner = config.own("collector", directory=tmp_path / "crew")
    with pytest.raises(SystemExit, match="already owns"):
        run(config.Config(), tmp_path / "crew")
    waiting = threading.Thread(
        target=config.own, args=("collector", True, tmp_path / "crew"), daemon=True)
    waiting.start()  # a standby copy waits for the owner instead of exiting
    waiting.join(0.3)
    assert waiting.is_alive()
    owner.close()
    waiting.join(5)
    assert not waiting.is_alive()


def test_native_records_reach_the_page_grouped_by_repository(tmp_path, service, monkeypatch):
    """Real adapter, real Git identity, real HTTP API: transcript to snapshot."""
    for path in ("mini/crew", "book/crew"):
        repo = tmp_path / path
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        subprocess.run(["git", "-C", repo, "remote", "add", "origin",
                        "git@github.com:mascah/crew.git"], check=True)
    monkeypatch.setattr(collector_module, "CodexAdapter", lambda *a, **k: FakeAdapter("codex"))
    monkeypatch.setattr(collector_module, "HermesAdapter", lambda *a, **k: FakeAdapter("hermes"))
    collectors, homes = {}, {}
    for machine in ("mini", "book"):
        home = homes[machine] = ClaudeHome(tmp_path / machine / "claude")
        cfg = config.Config(machine_id=machine, machine_name=machine, claude_home=str(home.root))
        collectors[machine] = Collector(cfg, tmp_path / machine / "state", Link(service))
        home.cwd = str(tmp_path / machine / "crew")
        home.registry("busy")
        home.prompt("Fix it")
        home.tool("Bash", {"command": "pytest", "description": "Running tests"})
    for machine in ("mini", "book"):
        collectors[machine].tick(homes[machine].clock)
    snapshot = service.snapshot()
    assert {(s["machine_id"], s["activity"]) for s in snapshot["sessions"]} == {
        ("mini", "Running tests"), ("book", "Running tests")}
    assert len({s["project_id"] for s in snapshot["sessions"]}) == 1  # one repository, two Macs
    assert [p["detail"] for p in snapshot["projects"]] == ["github.com/mascah/crew"]

    home = homes["book"]
    home.tool_result()
    home.say("All green.")
    home.system("turn_duration")
    home.registry("idle")
    service.now = home.clock  # the fixture transcripts carry real wall-clock times
    collectors["book"].tick(home.clock)
    [item] = service.completions()["items"]
    assert (item["machine_id"], item["session_id"]) == ("book", SID)
    detail = service.client.get(f"/api/completions/{item['id']}", headers=VIEWER).json()
    assert detail["response"] == "All green."
    states = {s["machine_id"]: s["state"] for s in service.snapshot()["sessions"]}
    assert states == {"mini": "working", "book": "idle"}


def test_text_cut_mid_character_is_still_stored_and_sent(tmp_path, service, link):
    adapter = FakeAdapter()
    collector = make(tmp_path, link, [adapter])
    adapter.sessions = [session(cwd=None, activity="Editing \ud83d")]
    adapter.completions = [completion(response="Done \ud83d")]
    collector.tick(T0)
    assert service.snapshot()["sessions"][0]["activity"] == "Editing ?"
    assert service.completions()["items"][0]["excerpt"] == "Done ?"
