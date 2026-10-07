# Collection sources for current activity and recent completions

Investigated 2026-10-06 using the local Mini installation, existing records,
installed Hermes source, and current primary documentation. The
[specification](spec.md) owns the agreed product behavior and collector setup.

This document preserves the sequence of the initial Mini-only review and the
later two-machine read-only inventory. Their no-probe/no-measurement statements
describe those passes. Subsequent live evidence belongs in the
[validation report](validation.md); the [reviewed decisions](spec.md#reviewed-decisions-for-issue-1)
and [remaining delivery checks](plan.md#remaining-implementation-and-release-checks)
describe the current shaping outcome.

## Question and recommendation

Can collectors recover current activity, waiting for the author, and finished
latest requests by reading existing data, or are observation hooks needed?

Existing records provide useful activity and completion evidence. Recommend
combining those records with observation hooks for timely lifecycle and waiting
signals. The author accepted observation hooks and the approach to limiting
overhead after its performance implications were explained. Hooks require configuration changes;
exact event coverage, behavior, and overhead on each installed CLI remain to
be validated before claiming complete support.

Reading only saved records remains an alternative if changing harness
configuration is undesirable. That would leave more states inferred or unknown,
especially approval/input waits. This investigation did not establish that every
waiting state is recoverable from records alone.

## Observations from this machine

The local package metadata identifies Codex `0.160.1`; the Claude launcher points
to version `2.1.292`. The Hermes source checkout is at `bd0affe5e`. These identify
the inspected installations, rather than a validated compatibility range.
All installation observations in this document are from the Mini. No MacBook
inspection has been performed.

For Codex and Claude, the last 512 KiB of each of the three newest main session
files was inspected for record types and schema keys. No conversation text,
commands, or final responses were printed. Samples are bounded evidence, not an
exhaustive catalog of lifecycle records.

| Harness | Local evidence observed | Implication and limit |
| --- | --- | --- |
| Codex CLI | Sampled rollouts contain `event_msg:task_started`, `event_msg:task_complete`, tool calls/results, messages, and session metadata. Completion payload keys include `turn_id`, `completed_at`, and `last_agent_message`. | Direct native request boundaries are available in these samples, with an apparent final-response field. Recovery and mapping still need implementation evidence; no approval-wait record was established by the sample. |
| Claude Code | Sampled transcripts contain assistant messages with `stop_reason` values `tool_use` and `end_turn`, plus `system:turn_duration` and `system:stop_hook_summary` records. | Saved tool activity and end-of-response evidence exist. Permissions, interruptions, and interactions between existing stop hooks require separate handling. |
| Hermes Agent | The checkpointed `state.db` schema has session IDs, cwd, Git repo root, profile, title, activity metadata, and message/tool fields. Installed code emits `on_session_end` with turn ID and completed/failed/interrupted fields at turn finalization. | The database can supply saved identity/history and the installed lifecycle code provides a candidate request-end event. Session `ended_at` alone does not represent every finished request. No message contents or live turn transitions were sampled. |

Sources inspected include native Codex/Claude session files under their configured
data directories; Hermes `hermes_state_common.py`, `agent/turn_finalizer.py`,
`agent/session_activity.py`, `agent/shell_hooks.py`, and
`hermes_cli/plugins.py` in `~/.hermes/hermes-agent`.

The Hermes database was opened with `mode=ro&immutable=1` only to inspect schema
columns. Uncheckpointed WAL updates were excluded; this was not a live database
state or message-content validation.

Existing user-level Codex and Claude hook files/configuration both name
`SessionStart`, `Stop`, and `UserPromptSubmit`. Only event names were inspected;
commands and trust state were not exposed or changed. This establishes that
existing hook configuration must be preserved, not that Crew's proposed hooks
have already been installed or proven to work.

## What primary documentation establishes

Codex documents lifecycle hooks including prompt submission, tool use, approval
requests, stopping, and interruption. Hook input includes session identity, cwd,
and event-specific fields. Hook definitions require review/trust; supported tool
hooks do not cover every tool path. `Stop` can request continuation, so a stop
callback by itself is not proof that a request has finally settled. These are
documented capabilities, not exercised installed-version behavior.
[Official OpenAI hooks documentation](https://learn.chatgpt.com/docs/hooks)

Claude documents tool/lifecycle hooks and immediate permission-request signals.
Network approval prompts have different coverage, including permission
notifications. Stop callbacks can also be used to continue work. Its collector
must account for the difference between stopping, continuation, and a finished
latest request. [Claude hooks reference](https://code.claude.com/docs/en/hooks)

Hermes documents hooks for CLI lifecycle, tools, approvals, and human-input waits.
The documented `on_session_end` canonical payload is emitted at turn finalization;
some exit paths have reduced payloads. The installed finalizer corroborates the
turn-level event. [Hermes hooks reference](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)

## Installed Hermes differs from current documentation

Current Hermes documentation includes `on_human_input_request` and
`on_human_input_resolved`. Neither name appears in the installed
`hermes_cli/plugins.py` valid-hook set. The installed checkout does have
`pre_approval_request` and `post_approval_response`, with call sites in the CLI
approval path.

Therefore, do not assume the documented generic human-input hooks are available
on this installation. A version update or another source may be needed for that
coverage. This is a documentation/installation difference, not a verified defect
in either project. Approval hooks also cover automated decisions, so an approval
event must be interpreted with its surface/outcome rather than automatically
labeled as waiting for a human.

The author permits updating Hermes if needed to obtain the required event
support. An appropriate version and upgrade method remain to be selected.
This investigation has not upgraded Hermes or changed its active sessions.

## Performance implications

Codex's default command hooks run synchronously; `async: true` lets supported
hooks run in the background. Background callbacks still create work and may
finish out of order; some lifecycle callbacks remain synchronous. Background
operation reduces waiting rather than eliminating resource cost.
[Official OpenAI hooks documentation](https://learn.chatgpt.com/docs/hooks)

Claude's default hooks also wait for completion. Command hooks can use
`async: true`; each invocation creates a separate background process. Process
startup and resource consumption still occur. Events may be lost at session
teardown, so asynchronous callbacks alone are insufficient for durable history.
[Claude hooks reference](https://code.claude.com/docs/en/hooks)

Hermes shell hooks spawn a subprocess for each matching event; plugin callbacks
run within the Hermes process. Its documented human-input observers run on the
thread entering the wait, and the documentation directs slow work such as
network calls to another thread. Installed shell-hook source corroborates the
subprocess mechanism. [Hermes hooks reference](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)

Consequences for Crew:

- Each inline callback contributes its runtime to the agent's operation.
  For illustration only, a 20 ms callback invoked serially 100 times adds
  2 seconds across those calls. This is arithmetic, not a local benchmark.
- A network request or retry in an inline hook can stall the agent when the
  Mini or tailnet is slow/unavailable. Emit locally and let the collector upload.
- Command/interpreter startup can cost more than the small event write itself.
  Minimize startup/import work, and consider in-process observers for Hermes.
- Background callbacks trade direct waiting for concurrent work, ordering, and
  teardown/recovery concerns. Keep even asynchronous callbacks short.
- Collectors cost CPU, memory, local reads/writes, and laptop battery. Use
  incremental record reads and batched reporting rather than repeated full-log
  scans or per-event network requests.
- Observation hooks should request no model work or add model-visible context;
  keep the normal prompt, continuation, and approval behavior with the harness.

Expected overhead for a small local event emitter is a hypothesis until measured.
No performance experiment or installed-hook timing was run. Measure callback
latency and aggregate collector resource use during representative concurrent
agent work before describing the impact as negligible.

## Collection design

The observation-hook design has been accepted after discussion of performance
implications. Behavior to deliver:

- Use per-harness callbacks to record available start, tool, wait, resume, and
  request-end signals. Read saved records to recover context and final responses.
- Have callbacks write a small local event record; let the background collector
  handle networking to the Mini. A server outage should not turn into a network
  wait inside an agent callback.
- Return the appropriate no-op result for each event. Do not inject instructions,
  ask for continuation, make permission decisions, or send prompts.
- Preserve existing hook configuration and the CLI's normal review/trust flow.
- Keep request outcome, session lifetime, and observation freshness separate.
  Detect continued/interrupted/failed requests before labeling completions.
- Display source gaps as unknown/degraded observation, rather than guessing that
  an agent is idle or that a request finished because output has been quiet.

These are design recommendations, not installed behavior or approved
production changes. No collector, server, or hook script has been written.

## Additional parent-child source evidence

A later read-only inventory on the Mini found 43 Codex rollout headers with
structured `source` objects. Of those, 31 exposed a nested field set containing
`parent_thread_id`, `depth`, `agent_path`, `agent_role`, and `agent_nickname`.
Those are useful parent-child identity inputs, not an exhaustive classification
of every subagent source form.

The Mini also had 324 Claude subagent metadata files beneath their main-session
directories. Sampled metadata keys included `agentType`, `spawnDepth`, and
`toolUseId`; parent-session placement comes from the nested transcript path.
Current Claude documentation describes `agent_id` on subagent tool hooks and
`agent_transcript_path` on subagent stop hooks. Its delivered subagent report can
come from `SubagentHandback` separately from the closing message, so response
recovery must distinguish them. [Claude hooks reference](https://code.claude.com/docs/en/hooks)

Installed Hermes `tools/delegate_tool.py` constructs child session and subagent
identities, emits `subagent_start` with the parent/child IDs, and records
`_delegate_from` in child model metadata. Its child session `parent_session_id`
is therefore supported by an explicit delegation marker; a parent link alone
also appears in other session lifecycle operations and is not sufficient to
classify all children as delegated agents. `tools/delegate_tool_results.py`
emits the corresponding child-stop hook.

These observations establish concrete candidate fields for the expandable view.
They do not prove that the collector handles every live, resumed, nested,
interrupted, or externally sourced child correctly.

## Execution handoff and deferral

The author initially directed proceeding with technical validation, then
clarified that the Mini cannot SSH into the MacBook and deferred the probe checks
so implementation can continue from the MacBook. The MacBook can SSH into the
Mini. The [handoff](plan.md) carries the deferred validation into that work.

No prototype code or benchmark was produced before this deferral. No hook was
installed, no agent was invoked for validation, and Hermes was not upgraded.
The measured-overhead requirement remains outstanding on both Macs.

## Remaining validation

- Exercise collector event mappings during implementation from the MacBook.
  Record actual installed-version evidence before claiming supported coverage.
- Check a normal request, a long tool, a permission wait, a question for the
  author, an interruption, another stop hook continuing work, and a resumed
  conversation. Record coverage separately per harness.
- Verify subagent start/end signals and native parent-child identifiers for the
  agreed expandable view. Check that children are attached to the correct parent
  and are not duplicated as top-level sessions, including after a resume.
- Establish missing generic human-input coverage on the installed Hermes.
- Repeat the installation and source checks on the MacBook. Only this machine
  was inspected; no remote machine was accessed.
- Determine restart/backfill behavior for sessions already running before
  hooks are added, and how profile-specific configurations are discovered.

No harness was invoked, no model turn was requested, and no harness configuration
or database was changed. This work consists of record/schema inspection and
source/documentation research; it is not an integration check.

## Two-machine shaping inventory

Read-only follow-up on 2026-10-06 during shaping of
[issue #1](https://github.com/mascah/crew/issues/1). This extends the original
Mini-only investigation; it does not change that earlier investigation's scope.
The root working tree was clean on `main` at `c3a9d7d`, with one worktree.

| Execution machine | Codex CLI | Claude Code | Hermes Agent |
| --- | --- | --- | --- |
| MacBook Pro | `0.160.1` | `2.1.290` | No executable found on PATH or installation under `~/.hermes`. |
| Mac Mini, inspected over SSH from the MacBook | `0.160.1` | `2.1.292` | Source checkout still at `bd0affe5e`. |

Version commands and source/record reads succeeded. No harness conversation was
started, no hook was installed, and no active configuration was changed. Existing
Codex hook event names on the MacBook were `SessionStart`, `Stop`, and
`UserPromptSubmit`; Claude also configured `Notification`. Commands and private
conversation text were not printed or saved as evidence.

### Native record and relationship findings

- MacBook: inspected bounded tails of eight Codex and eight Claude transcript
  files. Codex samples exposed `task_started`, `task_complete`, and item/tool
  records. Completion fields included `turn_id`, `completed_at`, and
  `last_agent_message`. Claude samples exposed `end_turn`, `tool_use`,
  `stop_hook_summary`, and `turn_duration`.
- Mini: inspected bounded tails of five files per harness. Codex also exposed
  `turn_aborted` with `turn_id`, `reason`, and timing fields.
- MacBook Codex header inventory: 76 headers had
  `source.subagent.thread_spawn.parent_thread_id`, depth, path, nickname, and
  role fields; 107 had a different `subagent.other` form. Mini inventory: 31
  `thread_spawn` and 13 `other` forms. The inventories span historical CLI
  versions. They establish schema candidates, not installed-version coverage.
- Claude metadata inventory: 620 nested subagent metadata files on the MacBook,
  with `parentAgentId` present in six; 324 on the Mini, with `parentAgentId` in
  twelve. Other fields included `agentType`, `spawnDepth`, and `toolUseId`.
  Main-session directory placement supports the root association; sparse nested
  parent metadata needs runtime checks. Message `parentUuid` is not a substitute
  for a native agent relationship.
- Claude stop summaries in sampled MacBook records included `hasOutput`,
  `preventedContinuation`, `stopReason`, and hook-error fields. Their semantics
  have not been exercised with a continuing stop hook. The presence of these
  fields does not establish a canonical post-hook completion signal.

### Installed Hermes corroboration

Read the Mini's source without importing the application or opening its live
database. `hermes_cli/plugins.py`'s `VALID_HOOKS` includes session lifecycle,
delegation, approval, and `agent_loop_stopped` events. It still lacks
`on_human_input_request` and `on_human_input_resolved`;
`tools/human_input_hooks.py` is absent in that checkout.

`agent/turn_finalizer.py:771` invokes `on_session_end` with `session_id`,
`turn_id`, `completed`, `failed`, `interrupted`, and `turn_exit_reason`.
`tools/delegate_tool.py:326` emits the explicit parent/child session and subagent
IDs; line 311 writes `_delegate_from`. `tools/delegate_tool_results.py:366`
emits the matching child-stop event. `tools/approval.py:914` and line 917 bracket
the CLI approval function with approval observers; that function can return
`cancelled` without a delivered human prompt. Those calls therefore do not prove
that every pre-approval event represents an actual wait.

### Primary documentation checked

The fetched references describe current capability; source presence and live
compatibility must still be checked independently.

- [Official OpenAI hooks reference](https://learn.chatgpt.com/docs/hooks):
  subagent hooks use the parent's `session_id` and child's `agent_id`.
  `Stop` may continue work. Background callbacks can reorder, queue, and be
  cancelled at teardown; `SessionEnd` is synchronous. Permission policy hooks
  can decide before a human is asked. Generic paired human-wait events were
  not established by this reference.
- [Claude hooks reference](https://code.claude.com/docs/en/hooks):
  `SubagentStart` also runs on helper resume; subagent stop events can include
  internal agents. `SubagentHandback` can hold the delivered report.
  `PermissionRequest` lacks a tool-use ID, can run on a path that cannot prompt,
  and does not cover sandbox-network prompts. `Notification:permission_prompt`
  follows a waiting prompt after about six seconds. `Stop` excludes user
  interrupts, while `StopFailure` handles API errors. Asynchronous hooks can be
  cancelled during non-interactive teardown. These findings favor native
  reconciliation over labeling states directly from individual hook names.
- [Hermes observer reference](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks):
  `pre_llm_call` is turn-scoped; `on_session_end` is run-scoped;
  finalize/reset concern session identity. Paired human-input observers describe
  actual human blocking and exclude smart approval decisions. Their presence in
  documentation does not make them available in the installed checkout.

### Repository evidence and inference

Both Crew checkouts returned `git@github.com:mascah/crew.git` from
`git remote get-url origin`, and an absolute common directory from
`git rev-parse --path-format=absolute --git-common-dir`. Neither currently has
an additional Crew worktree, so worktree matching was not exercised here.

Git documents the common directory's relationship to shared repository data
and `remote get-url`'s expansion of URL rewrite configuration.
[Repository layout](https://git-scm.com/docs/gitrepository-layout),
[rev-parse reference](https://git-scm.com/docs/git-rev-parse), and
[remote reference](https://git-scm.com/docs/git-remote).
Using the common directory locally and a normalized remote with explicit
mappings across machines is Crew's proposed identity policy, not a universal
repository identifier supplied by Git.

### What this pass has not established

No latency, CPU, memory, energy, or collector measurement was run. No event
mapping was tested against a live request, human wait, continuing stop hook,
resumed helper, or restart. Source candidates and placement recommendations are
recorded in the [decision review](spec.md#reviewed-decisions-for-issue-1).

## Authorized live follow-up

After this read-only inventory, the author selected seven-day retention and
pixel avatars and authorized disposable live probes on both Macs. The
[validation report](validation.md) supersedes the inventory's no-runtime-evidence
limit for its specifically tested cases. It records native daemon/CLI evidence,
callback measurements, prototype collector resource use, failed experiments,
and source/version boundaries. The [probe artifacts](probes/README.md) remain
disposable; the production application is still unimplemented.

## Implementation foundation research

Reviewed 2026-10-07 after the author requested an explicit stack decision before
implementation. The six original source/product decisions remain intact. The
[specification](spec.md#implementation-foundations) owns the selected foundations
and retained comparison. This section records the earlier proposal research;
the following are source facts and limits, not runtime validation.

| Primary source | Capability or constraint relevant to the comparison |
| --- | --- |
| [FastAPI features](https://fastapi.tiangolo.com/features/) | Python API framework with typed validation, OpenAPI/JSON Schema and client-generation support. Its static-file support permits the built UI to share the API service. |
| [Python sqlite3](https://docs.python.org/3/library/sqlite3.html) | Standard-library interface to a local SQLite database. The deployed runtime's SQLite build still needs inspection. |
| [SQLite appropriate uses](https://www.sqlite.org/whentouse.html) | Device-local application storage is an intended use. One writer can write a database at a time; short serialized transactions fit the proposed Mini-owned writes. Do not mount one database across both Macs. |
| [React build options](https://react.dev/learn/build-a-react-app-from-scratch) | Vite can build a client-only React/TypeScript application. This route leaves routing/data fetching to the application; React generally recommends frameworks for broader requirements. Crew's single private dashboard makes a small client app a reasonable inference. |
| [Fastify validation](https://fastify.dev/docs/latest/Reference/Validation-and-Serialization/) | The TypeScript/Node alternative supports schema-based route validation and response serialization. A Python backend is not required by the accepted collection sources. |
| [Node SQLite](https://nodejs.org/api/sqlite.html) | Current documentation marks built-in SQLite stability as release candidate and exposes synchronous database APIs. A TypeScript implementation should choose its driver and supported runtime explicitly rather than assuming this API is mature on every Node version. |
| [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) | Proxies a local service privately to the tailnet; HTTPS must be enabled and tailnet access rules apply. Serving files/directories has macOS client-variant limits; the proposal proxies the Crew service instead. Existing Mini Serve/access configuration has not been checked in this pass. |
| [Apple launchd guidance](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) | Per-user agents load with login and end at logout. System daemons have different startup/user context; a LaunchAgent does not establish pre-login availability. No background job was installed in this pass. |

The recommendation is based on Crew's local evidence/reconciliation workload and
interactive view, not cross-stack performance measurements. The probe scripts
remain disposable and do not select Python for production by themselves. Exact
dependency versions, packaging on both Macs, resource use, and operational
behavior still need implementation evidence. No dependency was installed, model
probe launched, service configured, or production code written for this review.

### Platform Django tooling reference

Read-only review on 2026-10-07, after the author selected Python/FastAPI plus
React/TypeScript/Vite and pointed to `~/GitHub/mascah/platform-django` for tooling
inspiration. Inspected that working tree's root `pyproject.toml`, `package.json`,
`justfile`, application `package.json` and `openapi-ts.config.ts`, and
`e2e/playwright.config.ts`. This is current local-file evidence, not a clean
release or a claim that those commands passed.

Useful patterns are `uv` with locked Python dependencies, Ruff/mypy/pytest,
pnpm with locked JavaScript dependencies, ESLint/Prettier and TypeScript checks,
Playwright, small `just` entry points, and generating the TypeScript client from
an exported OpenAPI schema without requiring a running development server.
The root Python file also contains Django-only plugins/options, and the command
surface includes larger-platform services; Crew should adapt the relevant
patterns rather than copying that setup. Exact versions there are observations,
not compatibility recommendations for Crew.

### Operating decision evidence

The [foundation decisions](spec.md#implementation-foundations)
record author-reviewed choices; no operating choice was selected solely by this
research. [SQLite WAL documentation](https://www.sqlite.org/wal.html) describes
same-host storage, checkpointing, the durability difference between NORMAL and
FULL synchronization, and a WAL-reset fix in 3.51.3/later with specified
backports. Check deployed runtime support before choosing journal settings.
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) provides
private HTTPS proxying with tailnet policy and user identity headers; tagged
devices lack those identity headers. This supports separate viewer identity and
collector upload credentials. [Apple launchd guidance](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
distinguishes user-login agents from system boot daemons. The existing tailnet,
reboot/login behavior, and deployed resource usage have not been exercised here.

### Mini startup investigation

Read-only inspection over SSH on 2026-10-07, after the author directed Crew
startup to match when agents can run in the current Mini setup. No reboot,
logout, service restart, gateway/model request, or configuration change was
performed. Only sanitized launchd/process metadata was retained here; credentials,
commands from configuration, and native conversation records were not copied.

- Hermes revision remained `bd0affe5e`. Its installed
  `~/Library/LaunchAgents/ai.hermes.gateway.plist` specifies `RunAtLoad`,
  `KeepAlive.SuccessfulExit: false`, and session types `Aqua` and `Background`.
  No Hermes gateway LaunchDaemon was found in the system job domain or installed
  system plist locations. The matching installer source is
  `hermes_cli/gateway_launchd.py` and supports GUI/user background domains.
- The domain-explicit `launchctl print gui/501/ai.hermes.gateway` lookup failed,
  but context-aware `launchctl list ai.hermes.gateway` showed the loaded job and
  PID. The existing gateway PID metadata matched a live managed-Python process.
  The initial lookup was therefore not evidence that Hermes was stopped.
  Installed source itself documents domain-print limitations and context-aware
  checks. The osascript launcher runs a shell command; it is not Terminal UI
  automation.
- The Mini's Tailscale application identifies itself as
  `io.tailscale.ipn.macsys`, version `1.102.4`; the app/network-extension processes
  and login helper were present. [Tailscale's macOS variant comparison](https://tailscale.com/docs/concepts/macos-variants)
  says this standalone system-extension variant cannot run before login, while
  the separate `tailscaled` variant can. No Tailscale variant was changed.
- FileVault reported off and the system OpenSSH service was loaded. A manually
  started SSH/background agent is therefore a relevant lifecycle case even
  without a graphical login. Reachability before login through any particular
  network path was not exercised; the current tailnet client is login-dependent.
- A subsequent check of `/Library/Preferences/com.apple.loginwindow.plist`
  found `autoLoginUser` configured for the inspected account. No disabling flag
  was present in that file, and the corresponding system managed-preferences
  plist was absent. No account password or automatic-login credential file was
  read. Together with FileVault being off, this supports expecting the Mini to
  create its account session automatically after reboot. That is materially
  different from requiring a person to log in manually.

[Apple's launchd guidance](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
distinguishes user-session agents from boot-time daemons.
[Hermes gateway documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/index.md)
corroborates the per-user LaunchAgent arrangement and next-login startup.
[Webhook documentation](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/webhooks)
requires the gateway to be running. These support the inference that the
current arrangement needs a user session before Hermes and tailnet access are
ready. [Apple's automatic-login guidance](https://support.apple.com/en-us/102316)
explains that configured automatic login creates that session during startup.
The observed Mini settings therefore support expecting Hermes/Tailscale to
resume after reboot without a manual login, once automatic login and service
startup complete. This does not provide service before any user session exists,
and is not a measured reboot-to-ready result or confirmation of every webhook.

The selected Crew policy is per-user graphical and background/SSH activation,
with local recovery while reporting is unavailable. Actual SSH-only startup,
single-collector ownership, service login/restart behavior, and catch-up remain
release checks in the [handoff](plan.md#remaining-implementation-and-release-checks).
Include an actual Mini restart followed by automatic login and service readiness
in a future authorized operational window; do not change or test those settings
as part of this read-only investigation.
