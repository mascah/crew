# Implementation handoff: agent activity

Start with [resume.md](resume.md) for the local working-tree state and saved
evidence pointers. The six original decisions are reviewed in the
[specification](spec.md#reviewed-decisions-for-issue-1). The stack and operating
choices are settled in the [foundations](spec.md#implementation-foundations).
Remaining work is implementation and release validation.

The [specification](spec.md) owns product behavior and acceptance. This document
owns the implementation sequence and the context needed to continue from the
MacBook. The [collection investigation](discovery.md) records existing evidence;
the [Office review](../office-review/discovery.md) is predecessor research.

## Handoff state

- Initial product scope, project meaning, expandable subagents, collector
  arrangement, and observation-hook design are agreed.
- All six shaping questions have selected answers. Remaining empirical coverage
  and performance work is listed separately below; it does not require another
  product interview.
- The author selected Python/FastAPI and React/TypeScript/Vite, with
  `platform-django` as a tooling reference. Storage/outage recovery, serving/
  access and freshness defaults are accepted. Startup is selected to match
  existing harness user sessions, including graphical and SSH/background
  contexts. The author review checkpoint is complete; the six original
  decisions remain intact.
- The author intends to move implementation to the MacBook. Only the MacBook
  can SSH into the Mini; reverse SSH access is not available.
- The author subsequently selected seven-day history and pixel avatars, and
  approved disposable live probes on both Macs. Those probes and their measured
  evidence now exist; see the [validation report](validation.md) and
  [reproduction artifacts](probes/README.md).
- Collectors, service and page are implemented in `crew/` and `web/` and are
  deployed on both Macs; see [delivery status](#delivery-status).
- Codex/Claude hosted or daemon lifecycle and same-helper resume cases were
  exercised on both Macs; direct Claude TUI continuation and manual approval
  cases also passed. Other wait variants and recovery paths remain
  unvalidated. Hermes current-source input observers were exercised in scratch
  on the Mini; Hermes was not installed on the MacBook.
- Hermes on the Mini was updated on 2026-10-07 for the human-input observers.
  Existing harness hooks/settings must be preserved.
- Stack, SQLite storage/outboxes, private Tailscale Serve access restricted to
  the author's account, user-session startup, and freshness targets are selected
  in the spec. Current Mini Hermes and Tailscale are not unattended boot-time
  daemons, but the Mini has automatic login configured with FileVault off;
  expect user-session services to start after reboot without a manual login.
  Preserve that setup; a future change to boot services is separate.
  Office's implementation is not inherited by selecting these approaches.

## Start from the MacBook

1. Read the specification, validation report, and this handoff at the usable
   revision linked by [issue #1](https://github.com/mascah/crew/issues/1). The
   checkpoint contains the settled decisions and retained probe evidence;
   earlier revision `c3a9d7d` predates them. The specification owns requirements,
   and this plan owns delivery. Inspect the current working tree and preserve
   any later partial work before beginning implementation.
2. Inspect the MacBook's installed harness versions, data/config locations, and
   existing hook setup. Recheck the Mini from the MacBook through the existing
   SSH access when remote checks are needed. Keep secrets and raw private
   conversations out of committed evidence.
3. Use the [selected foundations](spec.md#implementation-foundations)
   and their operating behavior before beginning the
   collection/lifecycle path. Evidence-backed source selections already exist;
   record source mismatches and unresolved coverage explicitly.

## Delivery sequence

Use one implementation issue for the first version. These are increments within
that work, not separate overlapping parent/child assignments. Each increment
uses the [agreed acceptance](spec.md#acceptance-of-the-agreed-behavior).

### Delivery status

As of 2026-10-07, merged to `main`. Evidence and its limits
are in the [implementation validation](validation.md#implementation-validation).

| Increment | State |
| --- | --- |
| Validate collection | Built. Common model and all three adapters pass model-free fixtures; Claude and Codex were run read-only over the MacBook's real records; bounded live probes covered hosted Claude, standalone Codex, and one real Hermes turn on the Mini. |
| Deliver a usable activity view | Built. Service, storage, access roles and the page pass `just check`; the built page was exercised in desktop Chrome against demo and real data at desktop, tablet and phone widths. No physical phone or tablet has opened it. |
| Join the two Macs | Deployed with the author's approval: Mini service behind Tailscale Serve on HTTPS port 8787, collectors and hooks on both Macs, Hermes updated on the Mini with the observer plugin in each profile. See the [deployed checks](validation.md#deployed-two-mac-checks). |
| Record release evidence | Recorded for the deployed setup except what is listed as [not yet shown](validation.md#what-is-not-yet-shown): reboot and SSH-only startup, Hermes waits and delegation on real sessions, battery and sleep, and physical devices. |

The table below still lists every release check. Rows covered by automated
tests or by the deployed checks are answered in the validation report; the
items above remain open.

### Validate collection

Implement the common observation shape and adapters from the
[reviewed source and identity decisions](spec.md#reviewed-decisions-for-issue-1).
Preserve request outcomes, session lifetime, and report freshness as distinct
facts. Saved passing cases are inputs for adapter regression checks; they do not
prove that the adapter itself works. Reconcile selected sources through Crew's
observable interfaces, including delivered-response recovery.

Begin with model-free replay and controlled fixtures. A new live case needs a
specific evidence gap, bounded run, and stated usage cost; do not rerun the
passing matrix by default. Preserve existing hooks, active sessions, credentials,
and review/trust flows.

### Remaining implementation and release checks

These gates demonstrate selected behavior; they are not unresolved product
decisions. Use the [report](validation.md) for the exact tested surface/version
and its limits. Recheck compatibility when a binary or integration changes.

| Area | Remaining check | Required evidence |
| --- | --- | --- |
| Codex surfaces | Standalone CLI/`codex exec` outside the shared daemon; unsupported structured subagent source forms. | Version-specific observations establish activity, actual waits, liveness, settlement, and response recovery for each supported surface. Unavailable daemon status remains an explicit gap; no observation method resumes work. Mini denial coverage is still absent. |
| Claude waits and outcomes | TUI questions/elicitation, denial/cancellation, interruption, API failure, network/other permission variants, and wait correlation. | Actual wait opening and closure are distinguished from policy callbacks and `idle_prompt`; terminal evidence excludes partial/interrupted requests. Hosted `result` and TUI `turn_duration` are checked separately. |
| Hermes package compatibility | Update the Mini and install on the MacBook with the tested generic human-input observer contract; check approval/sudo and non-submitted outcomes, continuation/interruption, and helper resume. | Verify loaded package paths, observer presence, profile discovery, paired IDs/outcomes, and request boundaries on both Macs. The scratch source/dependency experiment is not a managed-package result or a supported version range. |
| Relationships and recovery | Multiple/nested/background helpers; restart while active; sessions already running before hook installation; profile-specific discovery; duplicate/delayed events and record truncation/replacement. | Replay and adapter checks retain one entry per native agent, evidenced parent links, and one final response per settled request. Targeted live cases fill only missing lifecycle evidence. |
| Project identity | Implement the selected policy beyond the simple GitHub fixture: forks, multiple/missing origins, SSH aliases, local remotes, moved repositories, submodules, explicit overrides, and offline cached mappings. | Model-free Git/config fixtures group intended clones/worktrees, keep ambiguous cases distinct, and preserve history identity when mappings/remotes change. |
| Completion storage | Retention expiry/cap, initial list and access to remaining responses, replay/reconnect deduplication, delayed uploads, and service restart. | Controlled-clock/storage checks through the service satisfy the [history acceptance](spec.md#acceptance-of-the-agreed-behavior); native histories remain untouched. |
| Deployed performance | Cold activation; full native callback path with observation on/off; history scans, storage, concurrency/backlog, upload retries, service outage, sleep/reconnect, and MacBook battery impact. | Report sample count, p50/p95/p99/max, cumulative delay, CPU/peak memory/I/O and recovery behavior on both Macs. Compare warm callbacks with the selected targets; report cold costs separately. AC-powered replay/prototype figures do not establish battery impact. |
| Page and two-machine delivery | Actual collector-to-service reporting, SSH execution attribution, stale reporters/adapter errors, final-response reading, stable pixel avatars, narrow layouts, and reduced motion. | Exercise the agreed acceptance on the deployed two-Mac setup and desktop/tablet/phone layouts using the stack, storage and serving choices selected in the foundation review. Exact character artwork can follow during page design. |
| User-session startup | Mini reboot followed by its configured automatic login, graphical and SSH-only/background activation, logout/relogin, crashes/restarts, and collecting while Tailscale/reporting is unavailable. | Verify one collector per machine across session types, recovery from native records/local outboxes, and service readiness once its user session and network are available. A `Background` plist declaration or automatic-login preference alone is not runtime evidence. Reboot/logout tests require a bounded operational window; boot before any user session is not promised. |

Record passing, failing, unsupported, and unexercised cases separately. Release
requires evidence for the promised behavior across both Macs and all three
harnesses; a missing signal must stay visible until resolved. Native probes,
synthetic replay, adapter checks, and deployed measurements are different kinds
of evidence and must remain labeled as such.

### Deliver a usable activity view

Build one usable local path from observation to stored state and the readable
page, including project grouping, expandable helpers, and recent request
responses. Validate the agreed behavior through the observable interfaces. Keep
the interfaces independent of Bench and harness-specific names/tool schemas.

Use the selected recent-history defaults in the specification. Pixel avatar
artwork and subtle motion can follow the readable presentation;
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
