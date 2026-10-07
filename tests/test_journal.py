import concurrent.futures
import json
import subprocess
from pathlib import Path

import pytest

from crew import journal

EMIT_C = Path(journal.__file__).with_name("emit.c")


@pytest.fixture(scope="session")
def emit(tmp_path_factory):
    binary = tmp_path_factory.mktemp("bin") / "crew-emit"
    subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-o", binary, EMIT_C], check=True)
    return binary


def run(emit, path, payload, harness="claude"):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return subprocess.run([emit, path, harness], input=data, capture_output=True, check=True)


def test_emits_only_listed_top_level_metadata(emit, tmp_path):
    path = tmp_path / "journal.jsonl"
    payload = {
        "prompt": 'private "session_id":"spoof" text ' + "x" * 200_000,
        "tool_input": {"session_id": "nested", "cwd": "/nested", "list": [{"reason": "no"}]},
        "hook_event_name": "Stop",
        "session_id": "s-1",
        "cwd": '/tmp/we"ird\\dir',
        "stop_hook_active": True,
        "last_assistant_message": "private response",
        "transcript_path": "/t/" + "p" * 5000,  # over the value cap: dropped
    }
    result = run(emit, path, payload)
    assert result.stdout == b"{}\n"  # the neutral hook result
    [event] = journal.Journal(path).read()
    ts = event.pop("ts_ns")
    assert ts > 1_700_000_000 * 10**9
    assert event == {
        "harness": "claude",
        "hook_event_name": "Stop",
        "session_id": "s-1",
        "cwd": '/tmp/we"ird\\dir',
        "stop_hook_active": True,
    }
    assert b"private" not in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600


def test_malformed_or_empty_input_still_neutral(emit, tmp_path):
    path = tmp_path / "journal.jsonl"
    for payload in (b"", b"not json", b'{"session_id": "unterminated'):
        assert run(emit, path, payload).stdout == b"{}\n"
    assert [e.get("session_id") for e in journal.Journal(path).read()] == [None, None, None]
    run(emit, path, b'{"cwd":"a\n1\nb","session_id":"s"}')  # raw newlines cannot split a record
    reader = journal.Journal(path)
    assert [e.get("cwd") for e in reader.read()][-1] == "a 1 b" and reader.bad_lines == 0


def test_write_failure_is_an_observation_error_not_a_hook_failure(emit, tmp_path):
    blocked = tmp_path / "journal.jsonl"
    blocked.mkdir()  # the journal cannot be opened for append
    result = run(emit, blocked, {"session_id": "s"}, harness="codex")
    assert result.returncode == 0 and result.stdout == b"{}\n"
    assert journal.Journal(blocked).take_errors() == {"codex": 1}
    assert journal.Journal(blocked).take_errors() == {}


def test_concurrent_burst_loses_nothing_and_reads_incrementally(emit, tmp_path):
    path = tmp_path / "journal.jsonl"
    reader = journal.Journal(path)
    seen = []

    def one(i):
        run(emit, path, {"hook_event_name": "Stop", "session_id": f"s-{i}"})
        return i

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i in pool.map(one, range(400)):
            if i % 50 == 0:
                seen += reader.read()
    seen += reader.read()
    journal.append(path, {"harness": "hermes", "event": "pre_llm_call", "session_id": "h"})
    seen += reader.read()
    assert sorted(e["session_id"] for e in seen[:-1]) == sorted(f"s-{i}" for i in range(400))
    assert seen[-1]["harness"] == "hermes" and reader.bad_lines == 0
    assert reader.read() == []


def test_partial_line_waits_and_compaction_resets(tmp_path, monkeypatch):
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b'{"a":1}\n{"a":')
    reader = journal.Journal(path)
    assert reader.read() == [{"a": 1}]
    with path.open("ab") as f:
        f.write(b'2}\n')
    assert reader.read() == [{"a": 2}]
    with path.open("ab") as f:
        f.write(b'1\n[]\nnot json\n')  # anything that is not a record is counted, not passed on
    assert reader.read() == [] and reader.bad_lines == 3
    monkeypatch.setattr(journal, "TRUNCATE_ABOVE", 1)
    reader.compact()
    assert path.stat().st_size == 0 and reader.offset == 0
    journal.append(path, {"a": 3})
    assert [e["a"] for e in reader.read()] == [3]
