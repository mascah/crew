# Crew workflow

Crew is a new project evolving the earlier Office project at
`~/GitHub/mascah/office`. Crew's product scope and implementation stack have
not yet been selected.

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

Use Office to understand prior behavior and choices. Record which of those
Crew adopts when shaping its scope; Office's frozen release requirements,
Bench execution protocol, and stack are reference material until selected
for Crew.

## Document paths

These are defaults for new work; create documents when useful.

| Purpose | Location |
| --- | --- |
| Discovery and research | `docs/work/<effort>/discovery.md` and supporting evidence |
| Specification | `docs/work/<effort>/spec.md` |
| Optional implementation plan | `docs/work/<effort>/plan.md` |
| Local ticket drafts, when needed | `docs/work/<effort>/tickets.md` |
| Domain terms | `GLOSSARY.md` |
| Consequential decisions | `docs/adr/` |

Keep related work together and follow links to the canonical specification
rather than duplicating requirements in plans or tickets.

## Tracking

- Tracker: GitHub Issues in [mascah/crew](https://github.com/mascah/crew/issues),
  selected by the caller. Issues are enabled for this repository.
- Git remote: `git@github.com:mascah/crew.git`.
- Use the existing `bug`, `enhancement`, and `documentation` labels for issue
  type where applicable. Coordination roles map as follows:

| Role | GitHub label | Availability |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Proposed; not present |
| `needs-info` | `question` | Existing; requests further information |
| `ready-for-agent` | `ready-for-agent` | Proposed; not present |
| `ready-for-human` | `ready-for-human` | Proposed; not present |
| `wontfix` | `wontfix` | Existing |

Record states without an existing role label in the issue body until their
labels are established. Setup records this mapping without creating labels
or changing issue readiness remotely. Recheck labels before applying them.

## Checks

Crew currently contains documentation only, with no application, build,
lint, or test commands configured. For documentation changes, review the
diff, verify instruction pointers and document links, and run
`git diff --check`. Check new untracked files as well, since they are absent
from the normal diff. Add concrete project commands here when the stack is
chosen; Office's tests currently validate Office.

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
