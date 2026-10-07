from conftest import T0, Service, completion, project, session

DAY = 86400.0


def test_roles_are_explicit(service):
    assert service.get("/api/snapshot", headers={}).status_code == 403  # no Serve identity
    stranger = {"Tailscale-User-Login": "x@example.com"}
    assert service.get("/api/snapshot", stranger).status_code == 403
    assert service.get("/api/snapshot").status_code == 200  # login matched case-insensitively

    assert service.client.post("/api/ingest", json={}).status_code == 401
    unread = service.client.post("/api/ingest", content=b"{not json")  # refused before parsing
    assert unread.status_code == 401
    assert service.report(token="wrong").status_code == 401
    assert service.report("mini", token="book-token").status_code == 403  # scoped to its machine
    assert service.report("mini").json() == {"accepted": 0}

    service.report(completions=[completion()])
    upload_only = {"Authorization": "Bearer mini-token"}  # reporting never grants reading
    for url in ("/api/snapshot", "/api/completions", "/api/completions/1"):
        assert service.get(url, headers=upload_only).status_code == 403


def test_snapshot_nests_helpers_under_evidenced_parents(service):
    service.report(sessions=[
        session("main", activity="Running tests", title="Fix bug"),
        session("helper-a", parent_id="main", activity="Reading model.py"),
        session("nested", parent_id="helper-a", state="idle"),
        session("orphan", parent_id="gone"),
        session("main", harness="codex", state="waiting"),  # same native id, another harness
    ])
    snapshot = service.snapshot()
    assert [(s["harness"], s["session_id"]) for s in snapshot["sessions"]] == [
        ("claude", "main"), ("codex", "main")]
    main = snapshot["sessions"][0]
    assert main["key"] == "mini/claude/main" and main["activity"] == "Running tests"
    assert [(h["session_id"], h["state"]) for h in main["helpers"]] == [("helper-a", "working")]
    assert [h["session_id"] for h in main["helpers"][0]["helpers"]] == ["nested"]
    assert snapshot["sessions"][1]["helpers"] == []


def test_a_silent_machine_is_shown_as_last_seen_not_current(service):
    service.report("mini", sessions=[session()])
    service.now += 25
    service.report("book", sessions=[session("b1")])
    service.now += 10
    machines = {m["id"]: m for m in service.snapshot()["machines"]}
    assert machines["mini"]["stale"] and machines["mini"]["last_seen"] == T0  # receipt time
    assert not machines["book"]["stale"]
    assert len(service.snapshot()["sessions"]) == 2  # retained, for the page to mark as stale
    assert service.snapshot()["stale_after"] == 30.0

    service.report("mini", sessions=[])  # reconnect: a fresh snapshot replaces the old one
    assert [s["machine_id"] for s in service.snapshot()["sessions"]] == ["book"]


def test_completions_deduplicate_by_request_identity(service):
    first = completion("r1", response="FIRST")
    assert service.report(completions=[first]).json() == {"accepted": 1}
    service.report(completions=[first, first])  # replay after a lost acknowledgment
    service.report("book", completions=[first])  # another machine's request is its own
    service.report(completions=[completion("r1", harness="codex")])
    assert service.completions()["total"] == 3

    service.report(completions=[completion("r1", at=T0 + 60, response="SETTLED")])
    service.report(completions=[completion("r1", at=T0 + 30, response="stale replay")])
    page = service.completions()
    assert page["total"] == 3 and page["items"][0]["excerpt"] == "SETTLED"


def test_history_expires_by_completion_time_and_cap(tmp_path):
    service = Service(tmp_path / "s.db", completion_cap=30)
    old = [completion(f"old{i}", at=T0 - 7 * DAY + 60 + i) for i in range(5)]
    service.report(completions=[*old, completion("expired", at=T0 - 7 * DAY - 1)])
    assert service.completions()["total"] == 5  # too old at upload: accepted, not retained

    service.now += 3600  # no new upload is needed for the seven days to pass
    assert service.completions()["total"] == 0

    recent = [completion(f"r{i:02}", at=service.now - i) for i in range(40)]
    service.report(completions=recent[:25])
    service.report(completions=recent[25:])  # the cap keeps the newest, whatever arrived last
    page = service.completions("?limit=100")
    assert page["total"] == 30 and len(page["items"]) == 30
    ids = [service.get(f"/api/completions/{i['id']}").json() for i in page["items"][:2]]
    assert [d["completed_at"] for d in ids] == [service.now, service.now - 1]
    assert service.get("/api/completions/999999").status_code == 404


def test_newest_twenty_first_and_every_retained_response_can_be_opened(service):
    long_response = "A long final response. " * 400
    batch = [completion(f"r{i:02}", at=T0 - i * 60, response=f"{i:02} {long_response}",
                        title=f"Request {i}") for i in range(45)]
    service.report(completions=batch[20:])  # delayed upload: older work arrives first
    service.report(completions=batch[:20])
    page = service.completions()
    assert page["total"] == 45 and len(page["items"]) == 20
    assert [i["title"] for i in page["items"][:2]] == ["Request 0", "Request 1"]
    assert len(page["items"][0]["excerpt"]) < 300  # the list carries excerpts only

    seen = []
    for offset in (0, 20, 40):
        seen += service.completions(f"?offset={offset}")["items"]
    assert [i["title"] for i in seen] == [f"Request {i}" for i in range(45)]
    last = service.get(f"/api/completions/{seen[-1]['id']}").json()
    assert last["response"] == f"44 {long_response}"

    service.restart()  # retained entries survive a service restart
    assert service.completions()["total"] == 45
    assert service.get(f"/api/completions/{seen[-1]['id']}").json()["response"] == last["response"]


def test_one_repository_is_one_project_across_machines(service):
    crew = "github.com/mascah/crew"
    service.report("mini", sessions=[
        session("a", project=project("mini", "/Users/m/crew", crew)),
        session("b", project=project("mini", "/Users/m/crew", crew)),  # worktree: same keys
        session("c", project=project("mini", "/Users/m/other/crew", "github.com/else/crew")),
        session("d", project=project("mini", "/Users/m/scratch/crew")),  # no usable origin
    ])
    service.report("book", sessions=[session("e", project=project("book", "/Users/b/crew", crew))],
                   completions=[completion(project=project("book", "/Users/b/crew", crew))])
    snapshot = service.snapshot()
    ids = {s["session_id"]: s["project_id"] for s in snapshot["sessions"]}
    assert ids["a"] == ids["b"] == ids["e"]
    assert len({ids["a"], ids["c"], ids["d"]}) == 3  # same folder name, distinct projects
    assert service.completions()["items"][0]["project_id"] == ids["a"]
    names = {p["id"]: (p["name"], p["detail"]) for p in snapshot["projects"]}
    assert names[ids["a"]] == ("crew", crew) and names[ids["c"]] == ("crew", "github.com/else/crew")
    assert names[ids["d"]] == ("crew", "/Users/m/scratch/crew on mini")  # told apart per Mac
    assert {s["session_id"]: s["checkout"] for s in snapshot["sessions"]}["e"] == "/Users/b/crew"


def test_identity_survives_remote_changes_and_explicit_mappings_win(service):
    crew, moved = "github.com/mascah/crew", "github.com/mascah/crew-renamed"

    def project_of(machine, folder, origin=None):
        service.report(machine, sessions=[session(project=project(machine, folder, origin))])
        current = service.snapshot()["sessions"]
        return next(s["project_id"] for s in current if s["machine_id"] == machine)

    original = project_of("mini", "/Users/m/crew", crew)
    service.report(completions=[completion(project=project("mini", "/Users/m/crew", crew))])
    assert project_of("mini", "/Users/m/crew", moved) == original  # cached: history not rewritten
    fresh = project_of("book", "/Users/b/crew", moved)
    assert fresh != original  # a moved remote is not adopted automatically

    service.store.map_key(f"origin:{moved}", original)
    service.store.map_key("git:book:/Users/b/crew/.git", original)
    assert project_of("book", "/Users/b/crew", moved) == original
    assert service.completions()["items"][0]["project_id"] == original
    listed = {view.id: keys for view, keys in service.store.projects()}
    assert f"origin:{moved} (explicit)" in listed[original]


def test_outage_queue_losses_are_exposed_per_machine(service):
    service.report("book", expired_total=3)
    service.report("book", expired_total=3)  # a replayed report does not count twice
    service.report("book", expired_total=5)
    machines = {m["id"]: m for m in service.snapshot()["machines"]}
    assert machines["book"]["expired_pending"] == 5
    service.now += 8 * DAY
    service.report("book", expired_total=5)
    assert service.snapshot()["machines"][0]["expired_pending"] == 0  # the gap has aged out
    service.report("book", expired_total=6)
    assert service.snapshot()["machines"][0]["expired_pending"] == 1  # only the recent loss
    service.report("book", expired_total=2)  # the collector's queue was rebuilt
    assert service.snapshot()["machines"][0]["expired_pending"] == 3
