# Discord project attribution and container session coverage

Tracking: [Hermes attribution (#2)](https://github.com/mascah/crew/issues/2) and
[container observation (#3)](https://github.com/mascah/crew/issues/3).

Status: scope shaped on 2026-10-08. Independent container sessions and no factory
controller coupling are selected. The author also plans Codex sessions in Docker
and wants to avoid unnecessary complexity. Standard container setup exposing native
history and Crew hook events is selected. Initial Docker coverage is automated
Claude and Codex commands; interactive Docker terminals are deferred. Live state
coverage still needs validation. Implementation and deployment are pending.
The [original activity specification](../agent-activity/spec.md) continues to own
the established machine, project, observation, and retention rules.

## Problem and verified evidence

The author reports that Hermes sessions started through Discord with the
`keyborg-factory` profile show no project, despite that profile's configured
workspace. Claude sessions launched by a Hermes-controlled factory inside
Docker also do not appear. The author plans Codex sessions in Docker as well;
the approach should cover both harnesses with a small operating/configuration cost.

Read-only inspection of the checkout and Mini found:

- `~/.hermes/profiles/keyborg-factory/config.yaml` sets `terminal.cwd` to
  `/Users/mascah/GitHub/mascah/keyborg`. The two inspected Discord session rows
  in that profile's `state.db` have null `cwd` and `git_repo_root` fields.
- Crew's deployed Hermes plugin reads process-global `HERMES_HOME` and
  `os.getcwd()`. The journal includes Discord events with the default Hermes
  home and gateway directory. These do not identify a routed profile's workspace.
- The Hermes adapter searches default/profile databases for saved session
  identity, but accepts an event's process cwd only for CLI sessions. It does
  not recover a gateway workspace from the owning profile, and stops looking
  up metadata once it finds the session row, even if its cwd is empty.
- Installed Hermes provides context-local home and terminal-policy readers:
  `hermes_constants.get_hermes_home()` and
  `tools.terminal_scope.terminal_env()`. Their use in Crew callbacks still
  needs behavioral validation, including concurrently routed profiles.
- Crew's Claude adapter discovers transcripts and live PID files under one
  configured host Claude home. Its host hooks are not installed in the factory
  image. Container PIDs cannot be checked as host Claude PIDs.
- The factory sources are at `~/factory/src/` on the Mini, with corresponding
  sources under `~/GitHub/mascah/keyborg/factory/`. `run-worker.sh` and
  `run-review.sh` invoke `claude -p --output-format stream-json --verbose`.
  The controller launches detached containers, collects `docker logs` into
  each run's host `log.jsonl` after exit, then removes the container. Foreground
  invocations already redirect the stream into a host log during execution.
- A running `keyborg-3` container had a host checkout mounted at `/work` and
  a handoff directory mounted at `/handoff`, with no Claude home mounted.
  A saved reviewer stream contained native session identity, `/work` cwd,
  assistant/tool records, and a terminal successful `result` with
  `is_error: false`. Only identity/status metadata and record shapes were
  inspected; no live model request was made.
- Crew's observation model and service tree resolve a parent within the child's
  harness. A Claude-to-Hermes relationship requires a richer explicit parent
  reference and UI/filter decisions, beyond discovering container sessions.

Hermes documents that profiles and workspaces are separate, with tool cwd
controlled by `terminal.cwd`; see its
[profile documentation](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/).
Docker's [bind-mount documentation](https://docs.docker.com/engine/storage/bind-mounts/)
describes the host/container path boundary used by these launchers.
Its [container-log reference](https://docs.docker.com/reference/cli/docker/container/logs/)
supports following native stdout and recovering available logs by timestamp.

## Intended behavior

### Hermes: repair project attribution

Capture the owning profile and effective session workspace at observation time.
Use authoritative session/runtime cwd when available, otherwise the identified
owning profile's resolved terminal cwd. Feed a local host workspace through
Crew's existing repository/folder resolver. Profile names remain context, not
project identities, and a gateway process cwd is not workspace evidence.

For the reported Discord session, the result should be Mini / Hermes / keyborg,
with `/Users/mascah/GitHub/mascah/keyborg` as its checkout. Fresh evidence must
be able to fill in missing metadata on an already observed session.

An unresolved profile, placeholder cwd, unavailable policy, or nonlocal backend
without a verified host mapping must leave the workspace unknown. Current
profile configuration must not silently rewrite old retained completions.

### Container sessions: standard history and hook setup

Initial Docker coverage is automated/headless commands such as `claude -p` and
`codex exec`, selected by the author on 2026-10-08. Interactive terminals inside
containers are outside this change; existing host-session coverage is separate.

The author selected independent sessions and explicitly does not want
Crew coupled to the factory controller. Treat that controller as an example of
a launcher, not a Crew integration contract.

Expose native session history and Crew hook events to the existing host collector
through standard container setup, accepted by the author on 2026-10-08. Give each
execution environment dedicated persistent host-mounted history/event directories
and container-compatible Crew hooks. Reuse existing Claude/Codex record parsers,
extend the collector to multiple sources, and handle container lifecycle separately.
Do not add a collector/service in every container.

This was selected over Docker stdout ingestion to reuse native parsers and preserve
source files after container removal. It costs standard container configuration;
live coverage and implementation size have not been validated.

Codex stores native transcripts in `$CODEX_HOME/sessions` according to
[official OpenAI documentation](https://learn.chatgpt.com/docs/reference/troubleshooting).
Claude documents session history beneath `CLAUDE_CONFIG_DIR` in its
[environment-variable reference](https://code.claude.com/docs/en/env-vars).
Use dedicated container data, without sharing the author's entire host harness
home or treating credentials as observation inputs. Mounting files alone is not
complete support: host PID checks and the host Codex socket do not establish
container session state. Container-compatible hooks and appropriate lifecycle
evidence must fill that boundary or report an explicit gap.

Workspace mapping means recording two names for the same bind-mounted checkout.
For the inspected factory worker, the container's `/work` is the Mini's
`/Users/mascah/factory/jobs/keyborg-3/checkout`. An agent's reported `/work/src`
therefore corresponds to that checkout's `src` directory on the Mini. Different
containers can each report `/work` while using different host checkouts or projects.
Crew needs the source-specific association to inspect the correct repository and
show the real checkout. The standard setup should capture it from the workspace
mount and retain it with the observation source, avoiding manual per-job mappings.
The exact metadata-capture mechanism is an implementation choice to validate.

Keep Docker containers attributed to their execution Mac,
with container/run context available on the session. Key activity by harness and
native session ID; track container IDs separately so reused container names cannot
mix runs.
Separate new native identities on retry remain separate sessions; a verified
resume of the same native session preserves its identity.
Claude and Codex sessions appear independently under their execution machine and
project, without a Hermes parent relationship. They remain visible while the agent
runs even when the launching Hermes request has already finished.

Native harness completion evidence determines finished requests and retained responses.
Container exit, a controller's job state, and silence alone do not establish
successful response completion. A stopped stream or missing container exposes
an observation gap if no settled outcome is recoverable.

Mounted native history and hook events must survive container removal so the
collector can recover them after an outage. Persist their workspace association
with the source. Document the source's retention/cleanup boundary, reconcile live
state after reconnect, and keep completed responses within the original service
retention rules. Do not rely on factory-specific archives for recovery.

## Acceptance

### Hermes attribution

- A Discord session whose native cwd is absent is grouped under keyborg from
  its owning profile's effective local cwd. Two routed profiles do not leak
  workspaces into one another, and CLI/session-specific cwd remains correct.
- Existing sessions acquire a newly evidenced workspace without duplication;
  unresolved workspaces remain unknown and old history is not reassigned from
  today's configuration alone.
- CLI/session-specific cwd remains correct; an unavailable or nonlocal workspace
  without a verified host mapping is not replaced by the gateway's process cwd.

### Container observation

- Automated Claude and Codex container sessions appear under the execution Mac and
  their repository project while running, within the existing healthy-path
  freshness target. Their checkout is the host checkout, not a shared `/work`.
- A different launcher with the same supported harness/container evidence works
  without factory knowledge. Sessions appear independently under their own harness
  and do not require the originating Hermes session to remain active.
- Long tools remain working while execution is observed; unsupported waits or
  helper relationships are stated as gaps rather than invented.
- A successful native response is retained once. A timeout, kill,
  failed result, setup failure before the agent starts, or incomplete evidence does
  not create a successful finished request from partial assistant text.
- Collector restart and reconnect replay the mounted native history and hook
  evidence without duplicate completions. Container exit/removal preserves that
  source data for recovery and does not leave stale runs presented as live.
  Document the source's persistence and cleanup boundary with the standard setup.

### Shared observation constraints

- Observation preserves agent behavior and keeps networking outside callbacks.

## Selected decisions and validation

- Selected: independent Claude and Codex container sessions, grouped by execution
  machine and repository project, with no factory coupling or Hermes parent link.
- The author identified `~/GitHub/mascah/keyborg/factory` as the likely controller
  location, matching the sources inspected; it supplies evidence and an acceptance
  example, not a dependency.
- Selected after the Codex/simplicity feedback: shared native history and
  container-compatible Crew hooks through standard container setup. Docker stdout
  reading is an unselected alternative. Validate live state boundaries, removal
  races, checkpoint replay, waits/helper coverage, and
  resource overhead before claiming support.
- Selected: initial Docker support covers automated Claude and Codex commands.
  Interactive Docker terminals are deferred.
- Implementation validation remains: the source's live-state evidence and
  persistence/cleanup boundary must meet the acceptance above. These are technical
  validation requirements, not additional product-scope decisions or proof of support.

## Delivery

Two separate changes keep the attribution bug independent of new container support.
These are implementation steps, not completed work. Neither issue has a structural
dependency on the other; fixing Hermes first is a suggested delivery order.

1. **Hermes attribution:** update the observer/adapter to capture routed profile
   context and resolve an absent session workspace. Add regression cases for
   Discord, two profiles with different workspaces, CLI/session overrides, and an
   existing session gaining missing metadata. Run the project checks; validate the
   reported Mini case when the change is deployed separately.
2. **Container observation:** first validate the standard setup with one isolated
   automated Claude container and one automated Codex container, using generic
   launchers. Establish history/event mounts, saved workspace association, container
   lifecycle evidence, and supported wait transitions. Reuse these sources through the Mini
   collector, then exercise successful completion, forced termination, restart,
   replay, and removed-container history. Keep the source independent of factory
   code and avoid adding a service/collector to each container.

The container change covers automated commands only. Live probes follow the
bounded-probe policy with a stated gap and usage cost; this review has run no new
model turns. Deployment and live acceptance remain separate from local checks.

## Outside this proposal

No agent launching, Docker lifecycle control, prompts, approvals, factory
controller/job/PR integration, cross-harness nesting, interactive Docker terminals,
general remote-machine discovery, or cost reporting is added. Container coverage is
limited to the evidenced automated harness surfaces. Full live waiting/helper visibility
needs its own evidence. Any source integration observes existing work.
