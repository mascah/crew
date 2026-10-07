# Implementation handoff: agent activity

The [specification](spec.md) owns product behavior and acceptance. This document
owns the implementation sequence and the context needed to continue from the
MacBook. The [collection investigation](discovery.md) records existing evidence;
the [Office review](../office-review/discovery.md) is predecessor research.

## Handoff state

- Initial product scope, project meaning, expandable subagents, collector
  arrangement, and observation-hook design are agreed.
- The author intends to move implementation to the MacBook. Only the MacBook
  can SSH into the Mini; reverse SSH access is not available.
- Runtime/probe checks were deferred by the author during the Mini handoff.
  No prototype, collector, hook script, server, or page implementation exists.
- No performance benchmark, live harness integration check, or MacBook
  installation/source check has been run. Source observations are from the Mini.
- Hermes can be updated if required for selected event support. No update has
  been performed. Existing harness hooks/settings must be preserved.
- No implementation language, frontend framework, database, or tailnet serving
  mechanism has been selected. Choose these during implementation from the
  accepted scope and evidence; Office's stack is not a requirement.

## Start from the MacBook

1. Pull the Crew repository's `main` branch and read the specification and this
   handoff. Use the published implementation issue as a pointer to the usable
   revision, rather than treating an issue summary as the requirements owner.
2. Inspect the MacBook's installed harness versions, data/config locations, and
   existing hook setup. Recheck the Mini from the MacBook through the existing
   SSH access when remote checks are needed. Keep secrets and raw private
   conversations out of committed evidence.
3. Choose a small implementation stack and begin with the collection/lifecycle
   path. Source-backed candidates already exist, so a new product interview is
   not required. Record source mismatches and unresolved coverage explicitly.

## Delivery sequence

Use one implementation issue for the first version. These are increments within
that work, not separate overlapping parent/child assignments. Each increment
uses the [agreed acceptance](spec.md#acceptance-of-the-agreed-behavior).

### Validate collection

Establish a common observation shape and native identity mapping for the three
harnesses. Validate parent/child membership, current activity, human waits,
finished requests, interruption, continuation, and response recovery. Preserve
the distinction between request outcomes, session lifetime, and report freshness.

Start with controlled fixtures and replay of representative native records,
labeling simulated evidence clearly. Exercise actual hook integration and
representative work on the installed versions as implementation progresses.
Measure local callback latency and collector resource use on both Macs; keep
networking in the collector. A lightweight emitter measurement alone does not
measure harness serialization, interpreter startup, or the entire callback path.

The Mini has candidate child identity fields in Codex rollout metadata, Claude
subagent transcript placement, and Hermes delegation metadata/hooks. The
investigation also records a Hermes documentation/installed-version mismatch for
generic human-input hooks. Resolve these from current sources and runtime
evidence; update Hermes if necessary. Do not infer successful completion from
quiet output or a stop hook that another hook can continue.

### Deliver a usable activity view

Build one usable local path from observation to stored state and the readable
page, including project grouping, expandable helpers, and recent request
responses. Validate the agreed behavior through the observable interfaces. Keep
the interfaces independent of Bench and harness-specific names/tool schemas.

Choose bounded/configurable recent-history defaults during implementation and
document them. Artwork and subtle motion can follow the readable presentation;
they do not gate a usable first view.

### Join the two Macs

Run the Mini service and local collector, and a MacBook collector that reports
to it. Establish the stable tailnet address and macOS background operation.
Validate combined projects across clones/worktrees, SSH-started work attribution,
report retries, unavailable reporters, service restarts, and recent-response
recovery. Confirm that agent callbacks remain responsive when reporting fails.

### Record release evidence

Exercise the agreed acceptance across the actual two-machine setup and narrow
device layouts. Record per-harness lifecycle/subagent coverage and actual
overhead, distinguishing measurements, synthetic checks, and human observations.
Update the workflow with concrete checks once the stack and tooling exist.

## Scope boundaries

Keep the first version within the specification. Full transcript search, Bench
task accounting, usage/cost dashboards, exact time accounting, launching agents,
sending prompts, approving requests from the page, and scheduling are not part
of the agreed delivery. Discovery of an integration limitation does not select
one of these features or justify guessed activity; update the evidence and
choose a truthful observation/recovery approach.
