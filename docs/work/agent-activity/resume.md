# Resume Crew activity work

Updated 2026-10-07 after the first implementation pass on the MacBook. The six
shaping questions and implementation foundations are settled, and the
collectors, service and page now exist. Start here, then read
[spec.md](spec.md), [validation.md](validation.md), and [plan.md](plan.md).
Do not restart the product interview or repeat passing live probes.

## Implementation state

- Branch `implement-agent-activity`, pushed; not merged to `main`. Code in
  `crew/` and `web/`, tests in `tests/`. `just setup`, `just check` and
  `just build` are the whole local loop.
- **Deployed on both Macs** on 2026-10-07. Each runs from its own checkout at
  `~/Library/Application Support/Crew/app`, with `config.toml` (mode `600`,
  holding that Mac's upload token) beside it. The page is the Mini's Tailscale
  Serve address on HTTPS port 8787. Updating is `git pull`, `uv sync --no-dev`
  (plus `just build` on the Mini) in that checkout, then rerunning the
  `install` commands; see the [README](../../../README.md#run-it).
- On the Mini, tools such as `uv`, `pnpm` and `hermes` are only on a login
  shell's `PATH` (`zsh -lic` over SSH).
- Hermes on the Mini was updated from `bd0affe5` to `865ba906` with its own
  backup option; Crew's observer plugin is enabled in its three profiles.
- Codex shows newly added hooks for the author's review before running them.
  Until that is done on each Mac, Codex is observed from its daemon and
  rollouts, which already gives state, waits and finished requests.
- To remove everything: each `install` command takes `--remove`; the Serve route
  goes with `tailscale serve --https=8787 off`; the original harness settings
  are beside the edited ones as `.before-crew`.
- Open release evidence is listed under
  [what is not yet shown](validation.md#what-is-not-yet-shown).
- Claude Code keeps a live-session registry under `~/.claude/sessions/` that the
  probes did not cover; the adapter uses it for interactive session state. See
  the [validation note](validation.md#a-further-claude-source-the-live-session-registry).

## Mandate and decisions

The completed shaping pass resolved the six questions for GitHub issue #1 using
the shaping skill. The author selected seven-day completion history and pixel
avatars, then explicitly authorized disposable live probes on both Macs with
temporary hook configuration and model turns. Existing hooks and active sessions
must be preserved. That probe mandate did not authorize the production
application. The author subsequently authorized checkpointing/publishing the
reviewed documents and retained probe sources, and refreshing issue #1.
Implementation and deployment follow the caller's next instruction.

History defaults are seven days, a configurable 1,000-entry cap, and 20 entries
initially shown. Project meaning remains one repository across clones/worktrees;
use normalized origin and local Git common-directory identity with explicit
mappings. The selected stack is Python/FastAPI and React/TypeScript/Vite.

The [six-decision review](spec.md#reviewed-decisions-for-issue-1) records the
selected state/completion sources, callback placement, native helper identity,
repository identity, history defaults, and visual direction. Remaining work is
implementation and release evidence, owned by the
[handoff's checks](plan.md#remaining-implementation-and-release-checks).
Design resolution does not imply complete compatibility or delivered software.

The author subsequently rejected leaving the stack to the implementation agent,
then selected Python/FastAPI and React/TypeScript/Vite. The author pointed to
`~/GitHub/mascah/platform-django` for tooling inspiration. The
[four operating choices](spec.md#implementation-foundations) are settled:
SQLite/local durable queues, private Tailscale Serve access restricted to the
author's account, user-session startup including SSH/background contexts, and
the accepted freshness timings/queue bounds. The author directed startup to
match when agents can run in the existing setup. Hermes uses a user LaunchAgent
with `Aqua`/`Background`; the Mini's standalone Tailscale app cannot run before
login. The Mini has automatic login configured for the same account with
FileVault off, so both are expected to start after reboot without a manual
login. This has not been verified with a reboot. No services/login settings
were changed and no reboot/logout was tested. The six
original decisions and saved evidence remain intact.

## Evidence already obtained

- Codex `0.160.1`: passive reads over the existing Unix WebSocket daemon work on
  both Macs. A separate reader observed an actual approval wait and subsequent
  idle without resuming the thread. Native question waits, interruption,
  continuation, main resume, and same-child resume were also exercised.
- Claude: SDK/hosted cases and same-child continuation via `SendMessage` passed
  on both Macs. Direct TUI tests also passed: `turn_duration` appeared after a
  continuing stop hook settled; actual manual dialogs emitted `permission_prompt`
  and cleared after the fixture's approval. `idle_prompt` means readiness, not
  a blocked author request. Hosted permission waits did not emit that TUI signal.
- MacBook Claude runs used `2.1.290`; its normal TUI auto-updater changed the
  launcher to `2.1.292`. Mini runs used `2.1.292`. Keep that distinction when
  citing measurements.
- Hermes active Mini source remains recorded as `bd0affe5e`, without generic
  human-input hooks. Installed request/resume/delegation cases passed. Verified
  scratch source `7951ddd7297a284d6da48804241ee05a8a0c621c` emitted matching
  request/resolved IDs for an actual CLI clarify wait with submitted outcome.
  MacBook Hermes was not installed. The source experiment reused dependencies;
  it does not validate an official managed-package upgrade on both Macs.
- Corrected native writer timings, 43 samples per twenty-tool workload:
  Codex p95 11 ms MacBook / 15 ms Mini; Claude observed intervals p95
  12.642 ms / 19.609 ms. Cold launches took 166–283 ms. Both corrected journal
  stress runs consumed all 800 events; the first writer lost events and was fixed.
- Native Hermes dispatcher replay was model-free: Mini p95 0.157 ms, 200 events.
  The small journal prototype's resource measurements and limits are in the report.

## Artifact locations and caveats

The reviewed checkpoint consists of README, spec, discovery, plan, validation,
this handoff, workflow, and `probes/`. Inspect the branch and working tree on
resume and preserve any later changes.
The probe sources are disposable research artifacts, not production code.
Issue #1 is the single whole-spec implementation assignment and links the usable
checkpoint revision. Its earlier `c3a9d7d` handoff predates the probes and final
foundation choices. Ticket splitting is not an implementation prerequisite.

Scratch evidence remains at `/private/tmp/crew-validation-20261006` on both Macs;
the MacBook can reach the Mini through `ssh mini`. Raw wire/transcript/terminal
files must not be copied into committed evidence. Temporary Hermes `auth.json`
and `.env` copies in both scratch homes were removed on 2026-10-07. Active
credentials were untouched by that cleanup.
The scratch-only Claude folder-trust flag was also reverted on both Macs;
unrelated project trust, hook settings, and credentials were preserved.

The last automated `claude-tui-summary.json` records a failed driver attempt.
It does **not** represent the later successful direct-terminal tests. Those
native transcript IDs are:

| Case | MacBook | Mini |
| --- | --- | --- |
| TUI continuation | `d62aebc5-4ccf-48b1-a0a9-ab1f2526b41e` | `2fd316f4-ef48-4c1b-a068-7b77fc6f4151` |
| TUI permission | `0497304d-4924-4c3f-872f-59235d91ff0e` | `5af93e50-8fca-41d7-901f-e6a123814ebd` |

Their files live under
`~/.claude/projects/-private-tmp-crew-validation-20261006/<id>.jsonl`.
Hook metadata is in the scratch `claude-hook-inputs.jsonl`. These records were
rechecked without model calls on 2026-10-07, including in the final shaping pass.
The Python TUI driver needs a review
before reuse; use direct terminal control for its documented successful cases.

## Continue without another broad probe cycle

Documentation review and the short verdict for each original question are
complete, the foundation review is settled, and the first version is deployed.
The next pass closes the open release evidence. Use saved cases
for regression evidence and targeted
checks for the remaining gaps. Do not manufacture complete compatibility from
passing cases.

Remaining implementation/release gates include standalone Codex modes, Claude
interruption/network/other wait variants, nested/restart/backfill behavior, an
actual Hermes package on both Macs, cold activation, deployed collector overhead,
sleep recovery, and battery impact. They are not new product interviews.

The completed shaping review launched no new model probes. Existing probe
authorization
persists, but another live case should have a concrete evidence gap, a bounded
run, and a stated usage cost before execution. Never rerun the whole matrix by
default. Use model-free replay/analysis where it answers the remaining question.

Checks: `just check`, document links and `git diff --check`; Python syntax and C
warnings for retained probe artifacts. Keep generated bytecode and raw/credential files out of the
repository. The checkpoint and issue refresh are authorized; subsequent external
writes follow the caller's applicable instructions.
