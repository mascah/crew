"""The local hook journal: appended by callbacks, consumed by the collector."""

import contextlib
import fcntl
import json
import os
import time
from pathlib import Path

TRUNCATE_ABOVE = 4 * 1024 * 1024


def append(path: Path, event: dict) -> None:
    """In-process writer (the Hermes plugin). Same line format as crew-emit."""
    line = (json.dumps({"ts_ns": time.time_ns(), **event}) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        for attempt in range(6):  # shared: only a truncation can make us wait
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if attempt == 5:
                    raise
                time.sleep(0.001)
        os.write(fd, line)  # one O_APPEND write: atomic beside other appenders
    finally:
        os.close(fd)


class Journal:
    def __init__(self, path: Path, offset: int = 0):
        self.path = path
        self.offset = offset
        self.bad_lines = 0

    def records(self):
        """Yield records appended since the last read; a partial last line waits."""
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            self.offset = 0
            return
        if size < self.offset:  # replaced or truncated behind our back
            self.offset = 0
        if size == self.offset:
            return
        with self.path.open("rb") as f:
            f.seek(self.offset)
            for line in f:
                if not line.endswith(b"\n"):
                    break
                self.offset += len(line)
                try:
                    record = json.loads(line)
                except ValueError:
                    record = None
                if isinstance(record, dict):
                    yield record
                else:  # never let one bad line stop the collector
                    self.bad_lines += 1

    def read(self) -> list[dict]:
        return list(self.records())

    def compact(self) -> None:
        """Empty a fully consumed journal so it stays bounded."""
        if self.offset < TRUNCATE_ABOVE:
            return
        with self.path.open("rb+") as f, contextlib.suppress(BlockingIOError):
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)  # busy: try next poll
            if os.fstat(f.fileno()).st_size == self.offset:
                f.truncate(0)
                self.offset = 0

    def take_errors(self) -> dict[str, int]:
        """Callback write failures by harness since the last call."""
        errors = self.path.with_name(self.path.name + ".errors")
        counts: dict[str, int] = {}
        with contextlib.suppress(FileNotFoundError):
            data = errors.read_bytes()
            errors.unlink()
            for line in data.splitlines():
                with contextlib.suppress(ValueError, AttributeError):
                    harness = json.loads(line).get("harness", "unknown")
                    counts[harness] = counts.get(harness, 0) + 1
        return counts
