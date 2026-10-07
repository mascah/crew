# Disposable collection probes

These artifacts answer the source/lifecycle and overhead questions for issue #1.
They are experiments, not Crew's production collector, test suite, or selected
application stack. Results and limits belong in [the validation report](../validation.md).

## Reproduce the local cases

Use a private scratch directory and copy the scripts there. The recorded run
used `/private/tmp/crew-validation-20261006` on both Macs. The scripts resolve
their work directory relative to themselves; the Claude TUI transcript lookup
and Hermes checkout layout also assume this recorded directory.

```sh
mkdir -p /private/tmp/crew-validation-20261006
chmod 700 /private/tmp/crew-validation-20261006
cp docs/work/agent-activity/probes/* /private/tmp/crew-validation-20261006/
clang -O2 -o /private/tmp/crew-validation-20261006/emit /private/tmp/crew-validation-20261006/emitter.c
python3 /private/tmp/crew-validation-20261006/bench.py
```

`bench.py` requests no model turns. It measures process/emitter startup,
incremental journal consumption, an eight-worker burst, and disposable Git
clone/worktree identities. A burst is synthetic workload, not a running-harness
integration or a full deployed collector measurement. The writer has a bounded
five-millisecond lock retry and emits a neutral result; its fixed input buffer
and raw-payload journal are prototype simplifications. Production needs bounded
metadata extraction and explicit observation-error handling.

Live commands use installed authentication and request model turns. Run only
the selected bounded case, from the copied scratch scripts:

```sh
python3 /private/tmp/crew-validation-20261006/rpc_probe.py normal
python3 /private/tmp/crew-validation-20261006/rpc_probe.py permission
python3 /private/tmp/crew-validation-20261006/rpc_probe.py question
python3 /private/tmp/crew-validation-20261006/rpc_probe.py subagents
python3 /private/tmp/crew-validation-20261006/rpc_probe.py continuation
python3 /private/tmp/crew-validation-20261006/claude_probe.py normal
python3 /private/tmp/crew-validation-20261006/claude_probe.py permission
python3 /private/tmp/crew-validation-20261006/claude_probe.py subagents
python3 /private/tmp/crew-validation-20261006/claude_probe.py helper_resume
python3 /private/tmp/crew-validation-20261006/claude_probe.py continuation
```

Codex `resume` requires a preceding `normal` run. Claude `resume` requires
`normal`; `helper_resume` requires `subagents`. Both scripts also provide `tools`
for the twenty-command workload. Codex additionally provides `deny` and
`interrupt`. Claude's hosted permission/question cases use fixture responses;
they do not prove that a normal TUI emitted a human-wait notification. The
retained `claude_tty_probe.py` is a failed automation experiment, not the evidence
for passing TUI cases. Review it before reuse. Successful direct-terminal cases
and their native transcript pointers are recorded in [the resume handoff](../resume.md).

Codex command-hook definitions are reviewed by `hooks/list`, then their exact
hashes are supplied through invocation-only trust state. Existing persisted trust
and hooks are not rewritten. Claude uses invocation settings and an empty
setting-source list, preserving user files while isolating the experiment.
`continue_once.py` intentionally controls one continuation; the observer itself
does not. Native CLIs retain their own probe transcripts/session metadata.

`daemon_observer.py` opens the existing local Codex Unix WebSocket and only
initializes a connection, lists loaded threads, and reads metadata without turns.
It never resumes a thread, answers its requests, or starts a daemon.
`daemon_wait_fixture.py` deliberately creates one probe thread on an owner
connection; a second connection verifies its wait and idle state using reads.
Do not confuse this controlled writer with the passive observer.

## Hermes on the Mini

`hermes_probe.py` uses the installed managed Python and a scratch Hermes home.
It copies that host's existing credentials locally without printing them; remove
the scratch `auth.json` and `.env` files after use. Its observer plugin records
only identifiers/outcomes. `normal --revision installed`, then
`resume --revision installed` establish installed request and resume behavior;
`subagents --revision installed` tests delegation.

For the upgraded-source experiment, clone revision
`7951ddd7297a284d6da48804241ee05a8a0c621c` into the scratch `hermes-current`
directory. The experiment adds the pinned `ruamel.yaml==0.18.16` dependency to
scratch `hermes-deps` and reuses compatible installed packages. It deliberately
clears installed source modules after managed-runtime activation and asserts
the selected CLI/plugin module paths plus human-input observer presence. This
is not a full managed-package installation or compatibility-range test.

```sh
python3 /private/tmp/crew-validation-20261006/hermes_probe.py normal --revision current
python3 /private/tmp/crew-validation-20261006/hermes_probe.py question --revision current --tty
```

The TTY fixture supplies a normal terminal size, answers only its controlled
color question, and stops its own process at a bounded deadline. Check matched
request/resolved IDs and outcomes; a zero process exit alone does not prove a
request finished. `hermes_hook_bench.py` performs native dispatcher replay with
no model, using the current scratch profile and verified source modules.

Keep raw wire output, terminal output, authentication copies, and private native
records in scratch. Retain only sanitized assertions and aggregate measurements
in the repository. Restore the scratch-only TUI trust setting after the run;
leave unrelated settings and sessions intact.
