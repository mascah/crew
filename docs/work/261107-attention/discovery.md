# Attention and reach across both Macs

Discovery on 2026-11-07, from a conversation that started as "make the Mac mini
Claude workflow fluid" and found that the author's real wish is an attention
manager spanning both Macs, together with the direct git flow that moves work
between them. Its outcome is the draft [specification](spec.md). The author
agreed with the direction the same day and asked that moving work, the `mx`
command and direct git syncing between the Macs, be part of the effort rather
than beside it; the documents were revised accordingly.

## Question and destination

Can the author operate Claude Code sessions across the MacBook and the always-on
Mac mini as one set: know, wherever they are looking, which session needs them;
get alerted once and not again once they have seen it; get to, or type into,
that session from where they are; and move the work between the machines, a
mini branch onto the MacBook to verify, a fix back into the mini's worktree, a
local branch off to the mini, without GitHub or a screen share in the loop? Is
this a new project in `~/GitHub/mascah`, or a Crew increment? The destination was a requirements document future
conversations can be grounded in, not a build.

## Intended value

Three drawbacks of the current setup disappear: silent waits in tmux windows on
the mini, unnoticed finishes in background Ghostty tabs, and the slow hop of a
branch between the Macs through GitHub when a native app has to be run locally.
The author stops scanning two machines for the thing that needs them, and
verifying or fixing the mini's work becomes one action. Reference points the author
named: the "attention manager" idea in Josh Morony's tmux indicator, and the
sidebar UI of crmux, tailored rather than copied.

## What already exists

Observed on 2026-11-07 on both Macs unless stated.

- **Crew** (`~/GitHub/mascah/crew`) is deployed on both Macs: a collector on
  each reports to a service on the mini behind Tailscale Serve on port 8787, and
  a React page shows sessions by machine, harness and project with expandable
  helpers and recent completions. Its [specification](../agent-activity/spec.md)
  defines *working*, *waiting for the author*, *idle* and *unknown*, defines a
  completion as a settled request with its final response, and explicitly left
  "agent launching, sending prompts, acting on approvals, scheduling, or remote
  terminal control" to be "considered individually if the author wants them".
- The live snapshot at discovery time: both machines fresh, two MacBook Claude
  sessions (one of them the session doing this discovery, with two helpers), 411
  retained completions, the mini's Codex daemon not running. The API is readable
  from the MacBook with the author's Tailscale identity, so a MacBook client needs
  no new credential.
- Crew's Claude adapter already knows human waits from `Notification`
  `permission_prompt` and `elicitation_dialog`, from `Elicitation`, from a pending
  `AskUserQuestion`, and from the live registry's `waiting` status; the registry
  (`~/.claude/sessions/<pid>.json`) carries the process id, cwd, busy/idle/waiting
  status, the session name and a messaging socket path.
- **Terminal location is derivable without new hooks.** `ps -o tty= -p <pid>`
  on the registry's pid gave `ttys004` for the discovery session; the process
  chain was claude, zsh, login, Ghostty. On tmux machines `tmux list-panes -a -F
  '#{pane_tty} #{pane_id}'` maps that tty to a pane; Morony's scripts use the same
  match. Crew's hook writer copies only fixed payload keys, so `TMUX_PANE` from
  the hook's environment is not in the journal today; it is also not needed.
- **Ghostty 1.4 is scriptable on macOS.** Its AppleScript dictionary
  (`Ghostty.sdef`, `NSAppleScriptEnabled` set) exposes windows, tabs and
  terminals with `id`, `name`, `tty`, `pid` and `working directory`, and the
  commands `focus`, `select tab`, `activate window`, `input text`, `send key`,
  `new tab`, `new window` and `split`. A read-only probe listed six surfaces
  including both Claude sessions by tty, with the sessions' names in the surface
  titles. So a local session can be found by tty and focused, and text can be
  typed into it, with the author's local Ghostty habits unchanged. The
  `+new-tab` CLI reports "not supported on this platform".
- **tmux 3.6** on both Macs. Verified locally: a per-window user option set by
  pane id renders in `window-status-format` for the right window only, and
  `list-windows -f '#{!=:#{@claude},}'` filters to flagged windows. The mini's
  config has `allow-passthrough on`; `all` would forward escape sequences from
  windows that are not visible too.
- **Claude Code 2.1.319** on both Macs. Reading the binary: the `ghostty`
  notification channel emits a desktop-notification escape and wraps it in tmux
  passthrough when inside tmux; notification texts include "Claude is waiting for
  your input" and "Claude needs your permission to use X". The mini's settings
  leave the channel on `auto`, which inside tmux over SSH does not detect Ghostty.
  Hook matchers `permission_prompt` and `idle_prompt` exist, per the
  [hooks reference](https://code.claude.com/docs/en/hooks); `idle_prompt` fires
  about 60 seconds after a response if nothing was typed. The CLI also offers
  `--worktree` with `--tmux`, `--remote-control`, and `--bg` background sessions
  with `claude attach`, `claude agents --json`, `logs`, `stop` and `rm`.
- The author's Ghostty config is loaded (1.4 reads `config.ghostty`);
  `desktop-notifications` is on by default; `bell-features` defaults to
  `attention,title` on macOS.
- **memex** (`~/GitHub/mascah/memex`), the Tauri app that motivates local
  verification: `just app` runs `pnpm tauri dev` with Vite reloading the UI and
  Tauri rebuilding the Rust side on change; agent worktrees live under
  `.worktrees/<id>` sharing the root `target/`. The MacBook checkout had 21 such
  worktrees and the mini's checkout was a clean `main` with none, so the mini
  flow is new there. SSH host `mini` resolves over the tailnet and works
  non-interactively; `~/GitHub/mascah/<project>` is the same path on both Macs.
- Crew's checkout is on branch `factory/project-config`, two pushed commits
  ahead of `main`, with one uncommitted documentation change in
  `docs/work/261008-session-coverage/spec.md` that predates this discovery.

## Reference designs

**Josh Morony's indicator** ([source](https://www.joshmorony.com/workflows/handoff-claude-code-tmux-status-indicator.md)).
Hooks write `state|epoch|pane|cwd` per session under `~/.claude/status/`;
`UserPromptSubmit`, `PreToolUse` and `PostToolUse` mean running, `Notification`
`permission_prompt` means permission, `idle_prompt` and `Stop` mean done,
`SessionEnd` clears. A `.viewed-<id>` marker is set from tmux focus hooks
(`after-select-pane`, `client-focus-in` and others); a `.notify-<id>` marker
dedupes alerts and lets them be retracted with `terminal-notifier -remove` when
the pane is focused or the session runs again. The status line shows counts
first (`●N` working, `👁M` seen or idle) then names (`✋name` permission,
`✅name` done, capped at four). Alerts fire only when the terminal is not
frontmost. A `display-popup` with `fzf` lists live panes with a capture-pane
preview and switches to the chosen one. Persistence of alerts comes from a copy
of `terminal-notifier.app` with its own bundle id and alert style. Limits the
author states: single host only, "esc to interrupt" scraped from the pane to
detect working, hooks apply only to sessions started after install, macOS only.
Worth taking: the seen-by-focus idea, one alert per item with retraction, counts
before names, the jump switcher. Not worth taking: file-based state and TUI
scraping, since Crew already has the states and a service.

**crmux** ([repository](https://github.com/maedana/crmux), [crate](https://docs.rs/crate/crmux/latest)).
A Rust sidebar inside tmux listing Claude sessions with project, branch,
worktree, state, elapsed time, model and context percent; green running, orange
approval; a preview of the selected pane; `i` to type into the selected
session through `send-keys`, number keys to select, marks and broadcast. State
comes from Claude's `statusLine` command calling `crmux rpc status-update`, which
blanks Claude's own status line unless wrapped. Local tmux only, no hosts, no
worktree creation. The repository is in maintenance mode: no new features, and
compatibility with future Claude Code changes is not guaranteed. Worth taking:
the one-glance row and the sidebar placement. Not worth taking: the statusLine
hijack and local-only state.

Searching reddit.com directly was not possible from this session; the two
designs above are the ones the author pointed at. Related tools seen in the same
search: [tmux-window-notifier](https://github.com/mrf/tmux-window-notifier),
[Quickchat's two-line status bar](https://quickchat.ai/post/tmux-session-summaries-for-parallel-ai-agents),
claude-squad, ccmanager, workmux and dmux, all session or worktree managers that
own the git flow, which conflicts with the author's grove and `.worktrees`
practice; and [crystl.dev's account](https://crystl.dev/blog/tmux-setup-for-parallel-agents/)
of where hand-built tmux setups break, chiefly approvals and working versus done.

## Where it should live

| Option | For | Against |
| --- | --- | --- |
| Crew increment (recommended) | Owns both-machine observation, the states and completions attention derives from, the service where seen marks must live for cross-device agreement, the page the phone uses, deployment and checks. The list can be a `crew` subcommand. | Crew's README calls it "a readable web page"; the identity widens to include a terminal client and actions. |
| New project consuming Crew's API | Keeps Crew passive by construction; free choice of client language. | Duplicates model types; seen marks still need a server, so either a second service or Crew changes anyway; two deployments to keep in step. |
| Hooks and tmux only, no service | Zero infrastructure; the window flags and a `choose-tree` filter work today on each machine. | Single machine by nature, as Morony notes; no cross-device seen; no mini alerts while the author is not attached. Keeps its place as the in-tmux complement. |

Moving work is independent of this choice: `mx`, the `mini` remote and the
push setting are git and SSH, so they work with or without Crew. What Crew adds
is knowing which branch each session is on, whether its worktree is dirty, and
which MacBook checkout belongs to the same project, so the list can offer the
operations as one action.

## Mechanisms and their evidence

| Need | Mechanism | Evidence | Limit |
| --- | --- | --- | --- |
| Which session needs the author | Crew's `waiting` state and completions | adapter and model read; live snapshot | Hosted and Discord sessions have no terminal |
| Where a session's terminal is | pid from registry or process list, `ps` tty, tmux `pane_tty` match, Ghostty `tty` property | probe above | A session not in tmux or Ghostty has only a tty |
| Jump locally | Ghostty AppleScript `focus` on the terminal with that tty | dictionary read; `focus` not yet exercised | Requires Automation permission for the caller |
| Jump to the mini | Ghostty `focus` on the surface holding the SSH client, then `tmux select-window`/`select-pane` over SSH against the attached client | tmux semantics; SSH config `mini` works non-interactively | Needs the mini's tmux to be attached from that surface |
| Send text | Ghostty `input text` locally; `tmux send-keys` on the mini | dictionary; crmux practice | Keystroke-level, so approvals stay with jump |
| Seen by focus | Ghostty `selected tab` and `focused terminal` polled by the MacBook collector; tmux `after-select-pane`/`client-focus-in` hooks on the mini writing to Crew's journal | Morony's working hook set; dictionary | Polling interval bounds how fast seen clears |
| MacBook notification and retraction | `terminal-notifier` with a group id, or `osascript display notification` | Morony; both present on macOS or via Homebrew | Retraction needs the same posting bundle |
| Phone | Crew page, already reachable over the tailnet | deployed | No push; the page must be opened |
| Branch, worktree, dirty state | `git -C <cwd>` branch, common-dir and `status --porcelain` in the collector poll | standard git; memex layout read | Cadence versus cost on large repositories |
| Bring here | `git fetch mini` and fast-forward into the project's MacBook checkout | `mx` as designed; fetch over `ssh mini` works | Fast-forward only; Claude must have committed |
| Push back | `git push mini <branch>` with `updateInstead` on the mini | scratch-repository test, linked worktree and dirty refusal | Refused when the mini worktree is dirty, by design |
| Hand off | `git push mini`, `git worktree add` over SSH, `tmux new-window`, `claude` | each step standard; not yet exercised together | Worktree convention per project; conversation does not move |

Available today without any build, noted for the author: setting
`preferredNotifChannel` to `ghostty` in the mini's Claude settings makes
Claude's own waits and finishes reach the MacBook as macOS notifications while
attached; `allow-passthrough all` in the mini's tmux extends that to unselected
windows; the three-hook window flag from the conversation marks which tmux
window wants attention on that machine.

## Alternatives considered

- **Nested tmux**: a MacBook tmux whose windows include the mini attachment, so
  one `switch-client` reaches either machine. Rejected for now: Ghostty's
  scripting gives the same jump without changing the author's local habits or
  introducing nested prefixes.
- **Move local sessions into tmux**: one mechanism for both Macs. Possible later;
  not needed given Ghostty's dictionary.
- **Claude `--bg` sessions on the mini with `claude attach`**: persistence without
  tmux and attachment from any terminal. Claude-only and new in 2.1; the author
  values tmux panes for dev servers. Noted as compatible, not selected.
- **Claude Remote Control**: the same session from the Claude phone app when the
  laptop is closed. Complementary; outside this effort.
- **Web page only**: cannot focus a terminal. Kept as the phone surface.
- **Claude's per-session messaging socket** (`messagingSocketPath` in the
  registry): a native channel for sending text, but undocumented; `send-keys` and
  `input text` are the supported paths.

## Moving work between the Macs

The author's flow is direct git between the Macs, not GitHub round trips. The
conversation settled the mechanism before the attention manager came up, and the
author asked that it be part of this effort.

- **The mini as a git remote.** `git remote add mini mini:GitHub/mascah/memex`
  in a MacBook checkout; `git fetch mini` then sees every branch, including the
  ones checked out in the mini's worktrees, since branches belong to the
  repository. No GitHub push is needed for the MacBook to see Claude's commits.
- **Bring here.** The `mx` shell function: with no argument, list the mini's
  branches newest first; with a branch, fetch and fast-forward it into the
  current checkout, creating a tracking branch when new, refusing when diverged.
  With `just app` left running in the next Ghostty split, the checkout itself
  triggers the reload. The only habit it needs is that Claude commits before the
  author looks.
- **Push back.** With `receive.denyCurrentBranch updateInstead` set on the mini's
  repository, a push from the MacBook into a branch checked out in a mini worktree
  updates that worktree in place. Verified on 2026-11-07 in a scratch repository
  on the MacBook: the push into a branch checked out in a *linked* worktree
  updated its files, and a second push while that worktree had unstaged changes
  was refused with "Working directory has unstaged changes". So the mini's
  in-progress edits cannot be clobbered by this path.
- **Hand off to the mini.** The reverse, not yet exercised: push the local branch
  to the mini, `git worktree add` there under the project's convention, open a
  tmux window and start Claude in it. Claude Code's own `--worktree` flag uses its
  own worktree location, so the project convention has to come from
  configuration. Conversations do not move between machines.
- **Where the mini's branch lands.** Crew's project model already treats the main
  checkout and every worktree of a repository on both Macs as one project, so a
  mini session's project maps to the MacBook's checkout of it. The destination
  for bring here is the clone that is not itself a worktree, unless configured.
- **Dirty state in the list.** `git status --porcelain` on a session's checkout
  at a slow cadence tells the author whether bring here would get everything.
  Cheap for repositories of memex's size; cadence is an implementation knob.

Alternatives set aside: continuous two-way file sync (Mutagen, Unison) would
remove the commit step and make UI tweaks appear in the running app within a
second, but the author's one-worktree-per-change layout means one sync session
per worktree, a `.git` directory that must be excluded, and a mirror directory
the author cannot run git in; reconsider if commit-then-fetch proves too slow
for UI polish. Pointing the local Tauri dev window at a Vite server on the mini
would show frontend changes without any checkout but leaves the Rust side
stale. Both stay out of the first version.

## Unresolved questions and dependencies

The spec's [open questions](spec.md#open-questions) carry the product choices:
home, first-version reach, first-version movement, sidebar or popup, Ghostty or
tmux locally, banner or persistent alerts. Technical uncertainties still to
exercise, none of which changes the direction: Ghostty `focus` and `input text`
in practice, including the Automation permission prompt; selecting a tmux window
for the attached SSH client from an SSH command; seen-by-focus latency;
`terminal-notifier` retraction without Morony's bundle copy; hand off end to
end, including each project's worktree convention; the cost of dirty-state
polling on larger repositories. Dependencies: Ghostty 1.4 scripting,
tmux 3.6, Crew's deployed collectors and service, the author's SSH access to the
mini.

## Disposition

Continue, as a Crew increment unless the author prefers a separate project. The
draft [specification](spec.md) is the grounding document; the author agreed with
its direction on 2026-11-07 and asked for moving work to be included, which it
now is. Their answers to the open questions settle it. Slice 5 (moving work) is
git and SSH only and can be set up right away; slice 1 (session location) and
slice 2 (attention and seen) follow. No code, configuration or settings were
changed on either Mac during this discovery; the only writes are these two
documents, untracked, on the current `factory/project-config` branch.

## Sources

- [Josh Morony, multi-instance Claude Code status indicator for tmux](https://www.joshmorony.com/workflows/handoff-claude-code-tmux-status-indicator.md)
- [crmux repository](https://github.com/maedana/crmux) and [crate page](https://docs.rs/crate/crmux/latest)
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)
- [tmux-window-notifier](https://github.com/mrf/tmux-window-notifier)
- [Quickchat, live AI session summaries in a two-line tmux status bar](https://quickchat.ai/post/tmux-session-summaries-for-parallel-ai-agents)
- [crystl.dev, the tmux setup people build for parallel agents](https://crystl.dev/blog/tmux-setup-for-parallel-agents/)
- Crew: [activity specification](../agent-activity/spec.md), [plan](../agent-activity/plan.md), [resume notes](../agent-activity/resume.md), `crew/model.py`, `crew/adapters/claude.py`, `crew/emit.c`
- Local probes on 2026-11-07: Ghostty `+show-config`, `+list-actions` and `Ghostty.sdef`; `osascript` listing of Ghostty terminals; `ps` tty chain; tmux format and filter test; Claude binary strings; live Crew snapshot and completions; scratch-repository test of `receive.denyCurrentBranch updateInstead` with a linked worktree
- memex: `justfile`, `app/src-tauri/tauri.conf.json`, `.cargo/config.toml`, `.gitignore`, `git worktree list` on both Macs
