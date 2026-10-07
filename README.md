# Crew

A readable web page for understanding Claude Code, Codex CLI, and Hermes Agent
activity across a Mac Mini and MacBook Pro on a tailnet.

The agreed first version shows current activity by machine, harness, and project,
expandable subagents beneath their main sessions, and recently finished requests
with their final responses available to read. Collectors on both Macs report to
the Mini, which hosts the shared page. One repository groups its clones,
branches, and worktrees into one project.

## Project status

The six original design decisions for issue #1 have been reviewed against saved
validation evidence. Python/FastAPI with React/TypeScript/Vite is selected.
The [operating foundations](docs/work/agent-activity/spec.md#implementation-foundations)
are settled: SQLite with local outage queues, private account-restricted
Tailscale Serve access, user-session startup, and explicit freshness targets.
This repository contains the specification, source research, disposable probes,
measured results, and implementation handoff; the application has not been built.
Remaining source
coverage, package compatibility, recovery, and deployed performance checks are
separated in the handoff.

- [Specification](docs/work/agent-activity/spec.md)
- [Implementation handoff and delivery](docs/work/agent-activity/plan.md)
- [Saved validation evidence and limits](docs/work/agent-activity/validation.md)
- [Resume context](docs/work/agent-activity/resume.md)
- [Collection findings and validation limits](docs/work/agent-activity/discovery.md)
- [Office predecessor review](docs/work/office-review/discovery.md)
- [Agent workflow](docs/agents/workflow.md)
- [GitHub issues](https://github.com/mascah/crew/issues)
