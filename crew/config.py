"""Local configuration: one TOML file under the Crew home directory."""

import fcntl
import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def home() -> Path:
    return Path(os.environ.get("CREW_HOME", "~/Library/Application Support/Crew")).expanduser()


@dataclass
class Config:
    machine_id: str = "this-mac"
    machine_name: str = "This Mac"
    # collector
    service_url: str = "http://127.0.0.1:8787"
    token: str = ""
    poll_seconds: float = 2.0
    heartbeat_seconds: float = 10.0
    queue_days: float = 7.0
    queue_completions: int = 1000
    queue_bytes: int = 256 * 1024 * 1024
    claude_home: str = os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")
    codex_home: str = os.environ.get("CODEX_HOME", "~/.codex")
    hermes_home: str = os.environ.get("HERMES_HOME", "~/.hermes")
    # service
    port: int = 8787
    viewer_logins: list[str] = field(default_factory=list)  # Tailscale account logins
    collectors: dict[str, str] = field(default_factory=dict)  # sha256(token) -> machine id
    stale_seconds: float = 30.0
    retention_days: float = 7.0
    completion_cap: int = 1000


def load(path: Path | None = None) -> Config:
    path = path or home() / "config.toml"
    values = tomllib.loads(path.read_text()) if path.exists() else {}
    known = Config.__dataclass_fields__
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ValueError(f"{path}: unknown settings {unknown}")
    cfg = Config(**values)
    for name, value in values.items():  # `viewer_logins = "me@x"` must not become letters
        kind = type(getattr(Config(), name))
        if not isinstance(value, (int, float) if kind is float else kind):
            raise ValueError(f"{path}: {name} must be a {kind.__name__}")
    return cfg


def own(name: str, standby: bool = False, directory: Path | None = None):
    """Hold the single-instance lock for `name`; keep the returned file open.

    A LaunchAgent can be loaded by more than one session type. With `standby`
    the extra copy waits here and takes over if the owner exits.
    """
    directory = directory or home()
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory / f"{name}.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if not standby:
            raise SystemExit(f"another Crew {name} already owns this machine") from None
        logging.getLogger("crew").info("another %s owns this machine; standing by", name)
        fcntl.flock(lock, fcntl.LOCK_EX)
    return lock
