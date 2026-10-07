# Live collection validation for issue #1

Live probes run on 2026-10-06 after the author selected seven-day history, pixel avatars,
and disposable live validation on both Macs. The [specification](spec.md) owns
behavior; this report owns experimental evidence and limits. Reproduction
artifacts are in [probes](probes/README.md). No production collector or page was
built, and no active Hermes installation was upgraded.

## Saved-evidence review

On 2026-10-07, the final shaping pass reviewed the documentation and read saved
scratch evidence on both Macs without model calls or harness configuration
changes. No raw wire, terminal, transcript, or credential file was copied into
the repository. This rechecked existing results; it added no runtime coverage.

| Saved evidence | Review result |
| --- | --- |
| `daemon-wait-summary.json` on each Mac | A separate passive connection observed `waitingOnApproval`, then `idle` after a completed request. |
| `codex-tools-summary.json` and `claude-tools.wire.jsonl` on each Mac | The corrected writer's 43 samples per workload reproduced the native/observed timing figures below; unrelated Codex user hooks were excluded. |
| `benchmark-summary.json` on each Mac | Both bursts consumed 800/800 events with zero parse errors; idle CPU and peak driver/collector memory matched the report. All four simple Git identity assertions passed. |
| Direct TUI transcript IDs and hook metadata listed in [resume.md](resume.md) | Each continuation transcript had two stop summaries followed by one `turn_duration`. Each permission transcript had a `permission_prompt` and a terminal duration; later `idle_prompt` signals were distinct. The failed automated TUI summary was excluded. |
| Mini `hermes-current-question-tty-summary.json` | One actual clarify request and one resolution shared a request ID, with `outcome: submitted`. This remains scratch-source evidence. |

The [six-decision review](spec.md#reviewed-decisions-for-issue-1) records the
shaping verdicts. [Remaining implementation and release checks](plan.md#remaining-implementation-and-release-checks)
separately own missing source coverage, adapter/recovery checks, actual package
compatibility, deployed performance, and page acceptance.

## Installed versions and surfaces

| Machine | Codex | Claude Code | Hermes |
| --- | --- | --- | --- |
| MacBook Pro | CLI and running daemon `0.160.1` | Probed `2.1.290`; launcher auto-updated to `2.1.292` during normal TUI operation. | Not found on PATH or under `~/.hermes`; no installation performed. |
| Mac Mini | CLI and running daemon `0.160.1` | `2.1.292` | Active checkout `bd0affe5e`; newer source tested separately in scratch. |

Codex model work used its installed app-server protocol and existing
authentication. Claude used its real CLI with native hooks and stream-json
hosted input/permission control. Hermes used its real CLI and a passive Python
plugin in a private scratch profile. Hosted waits were held and answered by a
controlled fixture; they are live native requests, not observations of an author
clicking a normal terminal dialog.

## Codex: runtime status is the preferred live source

The existing control socket on both Macs accepts a **Unix WebSocket** connection.
The initial JSON-line, Content-Length, and length-prefix attempts failed because
they used the wrong transport. Neither the observer nor the transport checks
started, restarted, resumed, or changed an existing session.

Read-only `thread/loaded/list` and `thread/read` with `includeTurns: false`
returned native runtime statuses: the MacBook inventory included working and
idle threads; the Mini inventory included idle threads. A second, separate
connection read `activeFlags: [waitingOnApproval]` during a disposable owner's
real approval request, then read `idle` after its completion. This passed on
both machines. A collector can use these reads without resuming work.

Controlled native cases on both Macs established:

- A running request/tool emits active status; normal settlement emits idle and
  a completed turn. Session resume preserves its native thread ID.
- Human approval opens `waitingOnApproval` and a correlated server request;
  answering clears it. The MacBook denial fixture also cleared the request and
  completed the response cycle without executing the denied tool.
- A question opens `waitingOnUserInput`; its answer emits `serverRequest/resolved`
  and clears that flag. Both Macs exercised this path.
- An automated approval review can fire `PermissionRequest` while never opening
  a human-wait flag. Therefore that hook is not an accurate human-wait source.
- A controlled stop hook produced two assistant responses but one final parent
  turn settlement. Interrupting the disposable sleep produced `interrupted`,
  distinct from a completed request. Both cases passed on both machines.
- A child kept the same native agent/thread ID across two response cycles on
  both machines. Its two stop events carried distinct turn IDs. Parent and child
  completions must be correlated by thread ID; a child finishing does not settle
  its parent's request.

Prefer native runtime status for loaded daemon threads, and native turn/history
records for completion and backfill. `notLoaded` is not proof of idle. Coverage
of standalone `codex exec` processes outside the shared daemon remains a release
check; fallbacks must expose an observation gap rather than invent a wait state.
[Official app-server reference](https://learn.chatgpt.com/docs/app-server).

## Claude: request boundaries and helper identity

Both installed CLIs exercised a normal long tool, a native hosted approval,
`AskUserQuestion`, main-session resume, a helper, same-helper continuation through
`SendMessage`, and a continuing stop hook. The resumed helper retained the same
`agent_id` under the same main `session_id`. `Agent` has no `resume` parameter in
the tested tool surface; restricting away `SendMessage` made the first helper
resume attempt impossible. Enabling that native tool resolved it.

The hosted protocol's final `result` was delivered after stop-hook continuation.
Check `is_error` and the terminal reason, not only `subtype: success`: the first
Mini run returned that subtype with `is_error: true` and an expired-OAuth error.
The author renewed authentication, and the subsequent Mini cases passed.

Saved records recovered both responses in the continuation case. The
`hasOutput`, `preventedContinuation`, and `stopReason` fields were identical for
the first and final stop summaries. The first summary instead carried
continuation feedback in `hookErrors`. Those coarse flags alone cannot settle a
request, and errors/feedback should not be treated as typed terminal outcomes.

Direct terminal runs on both tested binaries subsequently established the normal
TUI boundary: two stop summaries and both response markers were followed by one
`system:turn_duration`. It appeared after continuation settled, while the CLI
remained open. Use that terminal record with the request's final assistant
response for the tested TUI surface. Early Python PTY attempts failed to
navigate startup trust and produced no transcript; they were excluded. Direct
terminal input through the normal scratch-folder trust dialog succeeded.

A seven-second hosted permission wait did **not** emit
`Notification:permission_prompt` in either tested stream-json run. Do not assume
the documented terminal-notification behavior covers that host surface. Actual
TUI runs on both Macs emitted `permission_prompt` while the harmless sleep
command's manual approval dialog remained open. Approving that exact fixture
was followed by `PostToolUse`, the expected response, and `turn_duration`.
Later `idle_prompt` notifications represented readiness for another request,
not a blocked human-input request. Network dialogs and interruption variants
remain release checks.
[Claude hook reference](https://code.claude.com/docs/en/hooks).

## Hermes: upgrade is required for generic waits

The active Mini version completed a real request, resumed that same session with
a new turn ID, and delegated one helper. `pre_llm_call`, `post_llm_call`, and
canonical `on_session_end` correlated the request. The latter carried a turn ID
plus `completed`, `failed`, and `interrupted`; `on_session_finalize` was a separate
session-lifetime event. Delegation supplied explicit parent/child IDs and a
matching stop event. These were real CLI/model calls.

Active source `bd0affe5e` lacks the generic human-input observer pair. The
scratch checkout at `7951ddd7297a284d6da48804241ee05a8a0c621c` contains it. An
initial reuse of the managed bootstrap loaded installed modules instead; those
runs were excluded from newer-version evidence. The corrected experiment
asserted current CLI and plugin paths and observer presence before model work.

With verified current source, a real classic-CLI color question emitted
`on_human_input_request(kind=clarify)` and `on_human_input_resolved` with the same
request ID, the correct session ID, and `outcome: submitted`, approximately two
seconds apart. The request then finalized normally. The CLI remained live and
idle until the probe's bounded shutdown. A non-interactive clarify call did not
establish a human wait, so a tool name alone is insufficient here as well.

Select a Hermes build with this observer contract. The active installation still
needs updating and the MacBook still needs an installation; test the actual
managed package on both machines. The scratch experiment reused installed
dependencies plus a scratch YAML package, so it is not a full upgrade or a
validated compatibility range. Approval/sudo outcomes, nested delegation, and
delegated-helper resume still require targeted release checks.
[Hermes observer reference](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks).

## Measured overhead

All values below are measurements, not proposed budgets. The native tool
workload made twenty separate harmless sleep calls per CLI. Each run supplied
43 new observation-hook timings; unrelated user hooks were excluded.

| Path | Machine | Samples | p50 | p95 | p99/max | Cumulative |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Codex native hook `durationMs`, corrected writer | MacBook | 43 | 6 ms | 11 ms | 12 ms | 314 ms |
| Codex native hook `durationMs`, corrected writer | Mini | 43 | 4 ms | 15 ms | 17 ms | 324 ms |
| Claude native hook-start to hook-response interval | MacBook | 43 | 5.993 ms | 12.642 ms | 14.060 ms | 324.546 ms |
| Claude native hook-start to hook-response interval | Mini | 43 | 12.756 ms | 19.609 ms | 21.952 ms | 450.231 ms |

Codex supplies a harness-reported interval; Claude values use the probe reader's
arrival timestamps and include local stream/reader scheduling. Neither measures
work before its start marker. These are small samples, not long-run percentile
guarantees. The warm samples fit the proposed 20 ms p95 / 50 ms p99 targets.

Cold costs do not fit those warm figures: the first native Codex writer invocation
on the MacBook took 283 ms. After rebuilding, direct emitter runs observed maxima
of 238.885 ms on the MacBook and 166.271 ms on the Mini. Do not call cold overhead
negligible or claim the full distribution meets the target.

The corrected direct emitter benchmark (200 processes each) measured p95
2.426 ms / p99 3.159 ms on the MacBook and p95 1.714 ms / p99 3.801 ms on the Mini.
It is an emitter-only microbenchmark, separate from the native intervals above.
Native Hermes dispatcher replay on the Mini wrote all 200 events: p50 0.092 ms,
p95 0.157 ms, p99 0.293 ms, max 7.341 ms. That replay requested no model and does
not establish MacBook Hermes performance.

The incremental journal prototype polled at 20 Hz for roughly eleven seconds:
idle CPU was 0.476% of one core on the MacBook and 0.362% on the Mini. The combined
benchmark/driver process peaked at approximately 22.2 MiB and 25.7 MiB respectively;
these include the producer driver, not only the collector. Under an eight-worker
800-event burst, both consumed all events with zero parse errors. An earlier
nonblocking-lock writer lost 44 events on the MacBook and 14 on the Mini; bounded
retry corrected this observed failure. Preserve that result when evaluating a
production journal/spool design.

The MacBook was on AC power. Battery drain was not measured. This is a small
incremental-journal prototype; native-history scanning, durable storage, upload
retries, sleep recovery, and the deployed service add work that remains to be
measured during implementation.

## Identity fixtures

Disposable Git fixtures passed on both machines: a worktree shared its parent's
absolute common directory; a separate clone did not; SSH and HTTPS spellings of
the same GitHub repository normalized together; another owner's repository with
the same folder name remained distinct. The real Crew clones also share origin.
Use that remote/common-directory mechanism with explicit mappings for missing,
ambiguous, or moved remotes. Do not merge by folder name, shared commits, or all
remotes combined. The fixture does not validate every provider's URL rules.

History and visual direction are design selections in the
[specification](spec.md#recent-history), rather than outcomes proved by these
experiments. Their storage and page acceptance checks remain in delivery.
