# Collection sources for current activity and recent completions

Investigated 2026-10-06 using the local Mini installation, existing records,
installed Hermes source, and current primary documentation. The
[specification](spec.md) owns the agreed product behavior and collector setup.

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
