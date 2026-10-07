# Live collection validation for issue #1

Live probes run on 2026-10-06 after the author selected seven-day history, pixel avatars,
and disposable live validation on both Macs. The [specification](spec.md) owns
behavior; this report owns experimental evidence and limits. Reproduction
artifacts are in [probes](probes/README.md). The probe sections below predate the
implementation; [implementation validation](#implementation-validation) records
what the built collectors, service and page have since been shown to do,
including the later Hermes update on the Mini.

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

## Implementation validation

Recorded on 2026-10-07 for branch `implement-agent-activity` (`crew/`, `web/`,
`tests/`). Five kinds of evidence are kept apart: automated fixtures, read-only
runs over the MacBook's real native records, bounded live probes, local
measurements, and [checks on the deployed two-Mac setup](#deployed-two-mac-checks).
The first four were gathered before anything was installed; the last after the
author approved deployment the same day. Open items are listed under
[what is not yet shown](#what-is-not-yet-shown).

### Automated fixtures

`just check` runs 91 Python tests plus the page's type-check, unit tests and API
contract check. All are model-free and use controlled clocks, temporary
directories, disposable Git repositories, a scripted Unix WebSocket server in
place of the Codex daemon, and the real FastAPI application through its HTTP
interface.

| Area | Tests | What they establish |
| --- | ---: | --- |
| Project identity | 16 | Worktrees share a project and clones join through one recognized origin; SSH and HTTPS spellings of the same host normalize together. A fork with an upstream remote, another owner's same-named repository, SSH aliases, non-default ports, local/file remotes, multiple origin URLs, a missing origin and a non-repository folder all stay distinct; a submodule is its own project. A removed worktree folder still resolves to its repository; a remote under a personal SSH user (`alice@host:repo`) stays local. |
| Hook journal | 5 | The compiled writer keeps only whitelisted top-level metadata, prints the neutral result for malformed or empty input, and turns a write failure into a recorded observation error rather than a hook failure; an eight-process burst loses nothing and is read incrementally; a partial last line waits, compaction resets the offset, and a raw newline or a non-record line cannot split or stop the reader. |
| Claude adapter | 16 | TUI settlement on `turn_duration`; hosted settlement on the stop summary plus session end, next prompt or quiet period; a blocked stop followed by continuation yields one completion with the later response; interruption, API failure and exit yield none; replay after restart does not duplicate. A permission prompt and a question open a wait and later evidence closes it, while `idle_prompt` does not; helpers nest by native agent ID (including a nested helper) and a resumed helper stays one entry; the live registry is authoritative for TUI state; a session with no liveness evidence is marked with its gap and becomes unknown, never idle; an unreadable transcript is reported while the rest continue. A response with no settling record (older TUIs, sessions without stop hooks) finishes after a quiet period and is replaced if a slow stop hook continues it; a helper that hands back its report is idle without a stop hook; a helper still running when the author sends another prompt stays listed; unexpected record or registry shapes cost one record, not the adapter. |
| Codex adapter | 18 | Daemon status maps to working/waiting/idle; rollouts give activity text and one completion per finished turn; aborted or empty turns give none; policy callbacks are not human waits; helpers attach only through an evidenced spawn parent; work outside the daemon is shown with an explicit gap; daemon loss is a stated gap while records still settle; replay after restart does not duplicate; the daemon client sends only read requests. A session spread over several rollout files, and a forked helper whose rollout repeats its parent's header, keep their own identity and every settled turn; one unreadable daemon thread does not blank the rest. |
| Hermes adapter and plugin | 8 | Turn open/close with a paired human-input wait; failed, interrupted and unfinished turns give no completion; delegated helpers nest under their parent while a plain parent link does not; the missing-observer gap is reported; sessions of a dead process leave; the plugin writes only bounded fields and never raises into Hermes. |
| Collector | 15 | One failing adapter does not blank the others; completions stay queued through a service outage and are delivered once; a lost acknowledgment replays without duplicates; the read checkpoint commits with the completions it covers; failed reports back off without stopping collection; queue age/count/size limits drop oldest with a visible count; backfill older than retention is skipped without being reported as loss; an unchanged machine stays fresh through heartbeats; a second collector on one machine refuses, or waits when started as a standby; real adapters through the real service group two checkouts of one repository as one project. A poll that fails after reading records is retried from the last saved checkpoint, including its journal events and across a restart; a later settlement replaces the queued one; text cut mid-character is still stored and sent. |
| Service | 9 | Viewer and collector roles are separate and a collector token reports only for its own machine; helpers nest under evidenced parents; a silent machine is shown as last seen, not current; completions deduplicate by request identity; seven-day and 1,000-entry retention; newest twenty first with every retained response openable; retained entries survive a service restart; an upload is refused before its body is read unless it carries a collector credential; one repository is one project across machines; identity survives a remote change and explicit mappings win; outage-queue losses are shown per machine, counted once under replay and only within the history window. |
| Installer | 4 | Hook entries are added beside existing ones, a repeated install changes nothing, removal restores the original file, no routine tool or policy-callback hooks are added, the installed command runs and writes only whitelisted fields, and the Hermes plugin installs and removes. A symlinked settings file stays a link with its mode; a neighbouring hook in the same entry survives removal; a mistyped setting is refused. |

### Read-only runs over real records

The adapters were pointed at this Mac's real `~/.claude` and `~/.codex` through a
scratch collector and loopback service with a scratch data directory. They read
only; no harness setting was changed.

| Observation | Result |
| --- | --- |
| First scan (seven days of records) | Claude 0.34 s, Codex 0.36 s; 156 finished requests recovered after the review fixes below (149 before them), each with a unique request ID. |
| Steady poll | Claude about 0.3 ms, Codex about 1.9 ms per two-second poll. |
| Live sessions | The implementing Claude session was shown working with its helper nested beneath it; a second Claude session and three daemon-loaded Codex threads were shown idle. |
| State tracking | A sampler compared Claude's live registry with Crew's reported state once a second: every observed `busy`/`idle`/`waiting` change, and each short-lived session that appeared and left, was reflected within one to two seconds. |
| Saved probe transcripts | Replayed through the adapter and service: neither `CREW_FIRST_STOP` (a blocked stop) nor `CREW_SHOULD_BE_INTERRUPTED` was listed as finished. |

### A further Claude source: the live-session registry

Claude Code `2.1.293` keeps one small file per running interactive session under
`~/.claude/sessions/<pid>.json` with `sessionId`, `pid`, `cwd`, `entrypoint`,
`status` (`busy`, `idle`, `waiting`), `waitingFor` and `statusUpdatedAt`. The
adapter treats it as the authority for an interactive session's current state
when the file exists and its process is alive, and falls back to transcript and
hook evidence otherwise (hosted sessions have no entry). This was found during
implementation and is not part of the earlier probe matrix. All three values were
observed live: `busy` and `idle` across turns, and `waiting` with
`waitingFor: "input needed"` while a question dialog was open, which Crew showed
as waiting within the same one-second sample and as working two seconds after
the answer. Permission dialogs were not sampled this way. It is an undocumented
file: if it is absent or its
shape changes, the adapter uses the hook and transcript path that the probes
validated.

### Bounded live probes

Each filled one stated gap, ran once, and used the production hook writer through
invocation-only settings (`--setting-sources ''` plus `--settings`), leaving the
user's own settings untouched.

| Gap | Run | Result | Cost |
| --- | --- | --- | --- |
| Hosted Claude through the built adapter | One prompt with an eight-second tool call | Shown working with its activity text throughout; one finished request, `CREW_HOSTED_OK`; the journal held only whitelisted fields. | $0.0231 |
| Hosted Claude stop-hook continuation | One prompt whose first stop is blocked | Only `CREW_SECOND_STOP` was listed as finished. | $0.0111 |
| Standalone `codex exec` outside the daemon | One short run | The daemon's loaded list did not change; the session was shown working with the stated gap that liveness and human waits are not observed outside the daemon, its activity appeared, `CREW_CODEX_EXEC_OK` was listed once, and the session left the view afterwards. | 6,635 tokens |

### Local measurements

Measured on the MacBook on AC power; these are not deployed figures.

| Measure | Result |
| --- | --- |
| Production hook writer, 200 launches with a 20 kB payload | p50 1.8 ms, p95 2.6 ms, p99 4.7 ms; the first launch after building took 232 ms. |
| Collector process | About 57 MiB resident, 0–1% of one core at a two-second poll. |
| Service process | About 57–84 MiB resident, under 1% of one core with one page open. |
| Journal burst | Writers take a shared lock with a 5 ms bounded retry; the eight-process burst test passed 30 consecutive suite runs. |

### Independent review

Two independent reviews read the whole change against the specification on
2026-10-07, one over the collector, service, hook writer and installer and one
over the adapters and page, each confirming findings with scripts it ran. The
defects they confirmed are fixed, each with a regression test counted above:

- A poll that failed after reading records could save its advanced checkpoint
  and lose finished requests; the outage queue kept the first of two settlements
  of one request; one malformed journal line could stop the collector.
- Codex sessions spread over several rollout files, and forked helpers, lost
  settled turns or showed a helper's turn as the author's (seen in this Mac's
  real records: four undelivered completions).
- Claude sessions that never write `turn_duration` (2.1.266, seen in real
  records) or a stop summary produced no finished requests.
- The installer replaced a symlinked settings file, widened its mode, and could
  remove a neighbouring hook; the loss counter double-counted on replay; the
  page's finished list could leave an unloadable gap after a long absence.

Accepted limits from the same reviews, left as they are:

- The viewer check trusts the identity header Tailscale Serve adds. A process
  already running as the author on the Mini can send that header to the loopback
  port; it can also read the database file directly.
- A checkout first seen without a usable origin stays its own project when an
  origin is added later, until mapped with `crew project`. This is the selected
  "a changed remote never rewrites history" rule.
- A hosted Claude session, or a Codex session outside the daemon, that is killed
  without a session-end callback keeps its last state for up to twelve hours
  with a stated gap; a long tool and a killed process look the same there.
- The page's rendering has no component tests; its grouping, filtering, paging
  and time logic do, and the rest was exercised in a browser.

### Deployed two-Mac checks

Deployed on 2026-10-07 with the author's approval, each Mac running from its own
checkout under `~/Library/Application Support/Crew/app`.

| Installed | Mac Mini | MacBook Pro |
| --- | --- | --- |
| Harnesses at the time | Claude Code `2.1.293`, Codex `0.161.0`, Hermes `v0.21.5+8877` at `865ba906` | Claude Code `2.1.293`, Codex `0.161.0`, no Hermes |
| Crew | Service and collector LaunchAgents; hooks appended to Claude and Codex settings (originals kept as `.before-crew`); Hermes plugin in the default, `grove-factory` and `keyborg-factory` profiles | Collector LaunchAgent; hooks appended to Claude and Codex settings |
| Serving | Tailscale Serve HTTPS port 8787 to the loopback service; the existing routes on 443, 9119 and 9999 were left as they were | Reports to that address |

Hermes on the Mini was updated with `hermes update --backup` from `bd0affe5` to
`865ba906`, which restarted its gateway and dashboard. The update printed one
warning (`Failed to load bundled provider plugin solstice: No module named
'httpx'`); the gateway and dashboard came back and a model turn ran afterwards.
All eleven observers the plugin asks for, including the two human-input ones,
were registered in each profile.

| Check | Result |
| --- | --- |
| One view, two machines | Both Macs reported within seconds; sessions carried their machine, harness and project; 307 finished requests were backfilled from both. |
| One repository, one project | The `crew` clones on both Macs resolved to one project, `github.com/mascah/crew`. |
| Access | From the MacBook through Serve the page and API returned 200; a request with a forged `Tailscale-User-Login` header was still answered as the author (Serve replaces it); the loopback port without an identity returned 403. |
| SSH-started Hermes on the Mini | `hermes chat --oneshot` started over SSH from the MacBook appeared under the Mini as working, then "Using terminal", with its folder; `CREW_HERMES_OK` was listed once and the session left. One short turn. |
| SSH-started Claude on the Mini | `claude -p` started over SSH, with the Mini's installed hooks, appeared under the Mini as working with "Pause for 8 seconds" through an eight-second tool; `CREW_SSH_CLAUDE_OK` was listed once; the session left at its `SessionEnd`. Cost $0.1107. The journal held only whitelisted fields. |
| Agents restart | `kill -9` of the Mini's collector and service: launchd restarted both and the page was current again within fifteen seconds, with retained requests intact. |
| One collector per Mac | A second collector started by hand exited with "another Crew collector already owns this machine". |
| A reporter stops | With the MacBook collector unloaded for 40 s the page marked it stale with its last-seen age while the Mini stayed current; reloading it restored it within ten seconds. |
| Service outage | With the Mini service stopped for about three minutes the page was unreachable, the MacBook collector backed off (2, 4 ... 60 s), and after the restart both Macs were shown as last seen until their next report, then current. No finished request was duplicated. No request finished during the outage, so the queued-delivery path was not exercised live. |
| Callbacks during the outage | 100 launches of the installed hook writer on the MacBook while reporting was failing: p50 1.8 ms, p95 3.4 ms, max 304 ms (the first). |

Deployed measurements, each over one minute unless stated:

| Measure | Mac Mini | MacBook Pro (on battery) |
| --- | --- | --- |
| Collector CPU | 0.7% of one core | 1.5% of one core, while one session changed on every poll and each report opened a new HTTPS connection |
| Service CPU | 0.25% of one core | — |
| Resident memory | Collector 43 MiB, service 58 MiB | Collector 44 MiB |
| Hook writer, 200 launches | p50 1.5 ms, p95 1.6 ms, p99 1.7 ms, max 2.0 ms | See the local measurements above |
| Adapter work per poll (profiled) | — | 7 ms of CPU; discovery of transcript files is the largest part |

After that outage check the retry ceiling was lowered from 60 s to 30 s so that a
restarted service sees each reporter within the stale threshold.

### What is not yet shown

- **Startup.** No reboot, logout or SSH-only session was tested. The agents are
  loaded in the logged-in user's session; that they come back after a Mini
  reboot with automatic login, or activate for an SSH-only session, remains a
  configuration-based expectation.
- **Codex hooks.** Codex asks the author to review newly added hooks before it
  runs them; until then Codex sessions are observed from the daemon and rollouts
  only, which is how every Codex result above was obtained.
- **Hermes.** One real turn with a tool call was observed on the Mini. Hermes
  human-input waits, delegation and resume have fixture evidence only, and the
  MacBook has no Hermes.
- **Battery and sleep.** One minute of CPU on battery is not a battery-impact
  measurement; sleep and reconnect were not exercised.
- **Devices.** The page was exercised in desktop Chrome at desktop, tablet and
  phone widths; no physical phone or tablet has opened it.
- **Claude wait variants.** TUI question/elicitation, denial and cancellation
  are covered by fixtures only.
- **Codex.** Denial on the Mini and unsupported sub-source forms beyond
  `guardian_review` are unexercised; the latter stay unattached by design.
- **Native callback intervals** as reported by the harnesses with the production
  writer installed. The figures here time the writer process itself.
