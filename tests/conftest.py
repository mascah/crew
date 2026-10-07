import pytest
from fastapi.testclient import TestClient

from crew import config
from crew.collector import token_hash
from crew.model import CompletionObs, ProjectRef, Report, SessionObs
from crew.service import Store, create_app

VIEWER = {"Tailscale-User-Login": "Author@Example.com"}
T0 = 1_800_000_000.0


class Service:
    """The service behind its real HTTP interface, on a controllable clock."""

    def __init__(self, path, **settings):
        self.path, self.now = path, T0
        self.cfg = config.Config(
            viewer_logins=["author@example.com"],
            collectors={token_hash("mini-token"): "mini", token_hash("book-token"): "book"},
            **settings,
        )
        self.restart()

    def restart(self):
        self.store = Store(self.path, self.cfg)
        self.client = TestClient(create_app(self.cfg, self.store, now=lambda: self.now))

    def report(self, machine="mini", sessions=(), completions=(), token=None, **extra):
        body = Report(machine_id=machine, machine_name=machine.title(), sent_at=self.now,
                      sessions=list(sessions), adapters=[], completions=list(completions), **extra)
        headers = {"Authorization": f"Bearer {token or machine + '-token'}",
                   "Content-Type": "application/json"}
        return self.client.post("/api/ingest", content=body.model_dump_json(), headers=headers)

    def get(self, url, headers=VIEWER):
        return self.client.get(url, headers=headers)

    def snapshot(self):
        return self.get("/api/snapshot").json()

    def completions(self, query=""):
        return self.get("/api/completions" + query).json()


@pytest.fixture
def service(tmp_path):
    return Service(tmp_path / "service.db")


def session(session_id="s1", harness="claude", state="working", **extra):
    return SessionObs(harness=harness, session_id=session_id, state=state, observed_at=T0, **extra)


def completion(request_id="r1", at=T0, response="Done.", harness="claude", **extra):
    return CompletionObs(harness=harness, session_id="s1", request_id=request_id,
                         completed_at=at, response=response, **extra)


def project(machine, folder, origin=None, name="crew"):
    keys = [f"git:{machine}:{folder}/.git"] + ([f"origin:{origin}"] if origin else [])
    return ProjectRef(keys=keys, name=name, checkout=folder)
