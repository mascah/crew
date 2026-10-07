# Crew workflow

Crew is a new project evolving the earlier Office project at
`~/GitHub/mascah/office`. The initial product scope and collector direction are
agreed in [the specification](../work/agent-activity/spec.md). The selected stack
is Python/FastAPI with React/TypeScript/Vite. Storage/recovery, private access,
user-session startup and freshness are selected in the
[implementation foundations](../work/agent-activity/spec.md#implementation-foundations).
The application lives in `crew/` (collectors, adapters, service) and `web/`
(the page); see [the handoff](../work/agent-activity/plan.md) for delivery state.

## Project references

- Project overview: `README.md`.
- Agent instructions: `CLAUDE.md`, with `AGENTS.md` symlinked to it.
- Workflow preferences: this file.
- Predecessor: [Office README](../../../office/README.md),
  [implementation context](../../../office/docs/blueprint/CLAUDE.md),
  [planning context](../../../office/docs/blueprint/CONTEXT.md),
  [product systems](../../../office/docs/blueprint/SYSTEMS.md), and
  [decisions](../../../office/docs/blueprint/DECISIONS.md).
- Office's code is in `../office/office.py` and `../office/office.html` relative
  to Crew's repository root. Its Bench contract and delivery records live in
  `../office/docs/blueprint/` and `../office/docs/plan/`.
- Tooling reference selected by the author: `~/GitHub/mascah/platform-django`.
  Consult its Python/JavaScript tooling and generated-client patterns as useful;
  adapt them to the selected Crew stack. Django-specific setup is outside Crew.

Use Office to understand prior behavior and choices. Record which of those
Crew adopts when shaping its scope; Office's frozen release requirements,
Bench execution protocol, and stack are reference material until selected
for Crew.

## Document paths

These are defaults for new work; create documents when useful.

| Purpose | Location |
| --- | --- |
| Discovery and research | `docs/work/<yymmdd>-<effort>/discovery.md` and supporting evidence |
| Specification | `docs/work/<yymmdd>-<effort>/spec.md` |
| Optional implementation plan | `docs/work/<yymmdd>-<effort>/plan.md` |
| Local ticket drafts, when needed | `docs/work/<yymmdd>-<effort>/tickets.md` |
| Domain terms | `GLOSSARY.md` |
| Consequential decisions | `docs/adr/` |

Keep related work together and follow links to the canonical specification
rather than duplicating requirements in plans or tickets.
Name a new effort folder with its creation date as `YYMMDD-<effort>`, for
example `261007-agent-activity`; later documents for that effort join the
existing folder. Existing undated folders stay as they are.

## Tracking

- Tracker: GitHub Issues in [mascah/crew](https://github.com/mascah/crew/issues),
  selected by the caller. Issues are enabled for this repository.
- Git remote: `git@github.com:mascah/crew.git`.
- Use the existing `bug`, `enhancement`, and `documentation` labels for issue
  type where applicable. Coordination roles map as follows:

| Role | GitHub label | Availability |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Existing |
| `needs-info` | `question` | Existing; requests further information |
| `ready-for-agent` | `ready-for-agent` | Existing |
| `ready-for-human` | `ready-for-human` | Existing |
| `wontfix` | `wontfix` | Existing |

Record states without an existing role label in the issue body until their
labels are established. Label availability above was checked on 2026-10-06;
this update did not create labels or change issue readiness. Recheck labels
before applying them.

## Checks

Run `just check` before handing over a change: Ruff, the Python tests, the
page's type-check and unit tests, and the generated API contract. `just build`
builds the page that the service serves; `just setup` installs the pinned
dependencies. The [README](../../README.md#develop) lists the tools needed.

Tests exercise behavior through the adapters' `poll`, the collector's `tick`,
and the service's HTTP API, using synthetic native records shaped like the
saved evidence. They request no model turns and read no real session data.
Live harness runs remain separate evidence: the
[probe README](../work/agent-activity/probes/README.md) owns the disposable
probes, and a new live case needs a specific gap, a bounded run, and a stated
usage cost. For documentation changes, review the diff, verify instruction
pointers and document links, and run `git diff --check`. Check new untracked
files as well, since they are absent from the normal diff.

## Isolation, commits, and execution

- Before writing, inspect the branch, working tree, and existing worktrees;
  preserve unrelated changes and stage only task-owned files.
- No Crew-specific branch or worktree convention has been selected. Follow
  the caller's isolation and commit instructions.
- This setup authorizes local workflow configuration. Commits, pushes, and
  external tracker writes need authority from the caller or an explicit
  caller policy.
- The calling agent executes work unless the caller selects another
  executor. Follow the caller's delegation and model preferences; this
  setup selects no agent roles or model routing.
- Codex-specific: If `gh auth status` reports an invalid token in the sandbox,
  rerun it outside the sandbox before concluding that GitHub CLI
  authentication is broken. In this checkout, the sandboxed check reported an
  invalid token, while the escalated check confirmed the active account was
  authenticated.

Edit this file to change preferences. Keep the managed `mascah-skills`
pointer in `CLAUDE.md` pointing here.
