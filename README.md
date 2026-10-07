# Crew

A readable web page for understanding Claude Code, Codex CLI, and Hermes Agent
activity across a Mac Mini and MacBook Pro on a tailnet.

The agreed first version shows current activity by machine, harness, and project,
expandable subagents beneath their main sessions, and recently finished requests
with their final responses available to read. Collectors on both Macs report to
the Mini, which hosts the shared page. One repository groups its clones,
branches, and worktrees into one project.

## Project status

Product scope and collection direction are agreed. This repository currently
contains the specification, source research, and implementation handoff; the
application has not been built. Runtime/probe checks and overhead measurements
are deferred to implementation from the MacBook.

- [Specification](docs/work/agent-activity/spec.md)
- [Implementation handoff and delivery](docs/work/agent-activity/plan.md)
- [Collection findings and validation limits](docs/work/agent-activity/discovery.md)
- [Office predecessor review](docs/work/office-review/discovery.md)
- [Agent workflow](docs/agents/workflow.md)
- [GitHub issues](https://github.com/mascah/crew/issues)
