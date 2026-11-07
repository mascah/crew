# Crew: attention, reach and moving work across both Macs

Status: drafted 2026-11-07 from the [discovery](discovery.md) and revised the
same day to include moving work between the Macs; the author agreed with the
direction and has not yet answered the [open questions](#open-questions).
Proposed as a Crew increment. The [activity specification](../agent-activity/spec.md)
continues to own machines, harnesses, projects, observation sources, session
states, completions and retention. This specification adds what the author
needs in order to *act* on that activity and to move work between the machines.
That specification listed sending prompts, acting on approvals and remote
terminal control as things to consider individually later; this is that
consideration.

## Problem

The author runs Claude Code on the MacBook, in Ghostty tabs and splits, and on
the always-on Mac mini, in tmux reached over SSH from the MacBook. Both Macs are
on the tailnet. Crew already shows what every session is doing. It does not tell
the author, wherever they happen to be looking, that a session somewhere needs
them, and it gives them no way to get there. Today a permission prompt on the
mini waits silently in an unselected tmux window, a finished request in a
background Ghostty tab goes unnoticed, and finding the right place means scanning
tabs on one machine and tmux windows on the other.

Work also has to move between the Macs, and today that is slow and by hand.
Claude on the mini commits to a branch in a worktree; verifying a native app
such as memex means that branch has to be on the MacBook; a fix made there has to
get back into the mini's worktree; and when the laptop is about to close, a local
branch should carry on on the mini. Each hop goes through GitHub, or through a
screen share. The author's ingrained flow is direct git between the two Macs,
with the mini as a remote of each MacBook checkout and an `mx` shell command
that fetches and checks out what Claude is working on; that flow is part of this
specification, not beside it.

The author wants an attention manager in the spirit of
[Josh Morony's tmux indicator](https://www.joshmorony.com/workflows/handoff-claude-code-tmux-status-indicator.md),
with the sidebar feel of [crmux](https://github.com/maedana/crmux), spanning
both Macs: one list of what needs them, alerts that arrive once and go away once
seen, a way to jump to a session or type into it from wherever they are, and
one action to bring a session's work here, send a fix back, or hand a branch off
to the mini.

## Intended behavior

### One attention list for both Macs

A list on the MacBook shows every live session Crew observes on either Mac,
ordered by need: sessions waiting for the author first, then finished and
unseen, then working, then idle. Each row names the machine, project, session
title, state and age, and for sessions in a git checkout the branch, the
worktree, and whether that worktree has uncommitted changes. It marks sessions
the author can jump to. The list is glanceable in a narrow Ghostty split beside
the terminals it refers to. The Crew page shows the same list for the phone and
iPad.

For example: Claude on the mini has stopped at a permission prompt in the memex
worktree `261107-abc12`; a MacBook session in grove finished a request two
minutes ago in a tab the author has not opened since; a second MacBook session is
editing a file. The list reads, top to bottom: `mini · memex · Transcript
order · needs you · 40s · fix/transcript-order · clean`, `book · grove · Living
engineering · finished · 2m · propose/261104-wd5rw · 3 changed`, `book · memex ·
Grove change · working · implement/261106-63w8e`.

### What needs attention

- **Needs you.** The session is in Crew's *waiting for the author* state: an
  actual permission prompt, a question or an elicitation. The activity
  specification's rules stand: an automatically answered permission check and
  ordinary readiness for the next prompt are not attention.
- **Finished, unseen.** The session's latest request settled into a Crew
  completion, no later prompt has been sent in that session, and the author has
  not seen it. An interrupted or partial response produces no item, exactly as
  it produces no completion.
- **Working** and **idle** sessions appear without emphasis so the list is also
  the overview. **Unknown** or **stale** observations show their age and never
  raise an alert.

### Seen means seen everywhere

An item becomes seen when the author focuses that session's terminal, sends the
session a new prompt, or acknowledges it from the list or the page. Seen is
recorded by the Crew service, so the MacBook list, the page on the phone and the
notification all agree. Focusing counts on both Macs: the Ghostty surface that
holds a local session, or the tmux pane that holds a mini session while the
author is attached to it. A new request in the same session starts a fresh,
unseen cycle.

For example: the grove session finishes while the author is on the mini. The
item is unseen. The author clicks into the grove tab to read the response: the
item clears, the notification retracts, and the phone page no longer shows it.
Had the author sent the next prompt from the phone instead, the same would hold.

### Alerts arrive once and retract

On the MacBook, a transition into *needs you* or *finished, unseen* produces one
macOS notification naming the machine, project and session title, unless that
session's terminal is focused and visible at that moment. The item being seen
retracts the notification. The same item never alerts twice. Nothing in the
list pulses or flashes; order, counts and age carry the urgency, in keeping with
the activity specification's quiet visual direction.

### Jump

Selecting an item takes the author to that session's terminal. For a MacBook
session, Ghostty focuses the surface running it. For a mini session, Ghostty
focuses the surface attached to the mini and that session's tmux window and
pane are selected there. The author's hands do the rest in the real terminal:
approving, answering, reading. A session with no terminal location, such as a
Hermes session driven from Discord, is listed but cannot be jumped to.

### Send text

From the list, the author can type one line that arrives in the chosen session's
terminal as if typed there, and is submitted. Nothing else is ever sent on the
author's behalf: approvals and dialogs are answered by jumping, not by injected
keystrokes.

### Work moves between the Macs without GitHub

Three operations, each one action from the list and each also a shell command
usable in any terminal. The list and the shell run the same code.

- **Bring here.** For a mini session, fetch its branch straight from the mini
  over SSH and fast-forward it into the author's checkout of that project on the
  MacBook, creating the branch when it is new there. A dev server already running
  in that checkout picks the change up on its own. The action refuses, and says
  why, when the destination checkout has uncommitted changes or the two branches
  have diverged; it never merges, rebases, resets or forces. When the mini's
  worktree itself has uncommitted changes, the row already says so, and bring
  here carries the committed work only. Today's `mx` is this operation's shell
  form.
- **Push back.** A commit made on that branch on the MacBook lands in the
  session's worktree on the mini with one action, so Claude sees the fix in
  place. The mini refuses it when that worktree has uncommitted changes, so
  Claude's in-progress edits are never overwritten; the list shows that refusal.
- **Hand off to the mini.** For a local session's branch, push the branch to the
  mini, open a tmux window there in a worktree for that branch following the
  project's convention, and start a Claude session in it. The conversation does
  not move; the new session starts fresh on the branch, and appears in the list
  as a mini session within the freshness target. Proposed for the first version;
  see [open question 3](#open-questions).

For example: Claude on the mini finishes "Transcript order" on
`fix/transcript-order` in memex, worktree clean. The author presses bring here;
the MacBook's memex checkout fast-forwards; `just app` in the next split rebuilds
and the window reloads. They find a one-line CSS fix, commit it, and press push
back; the mini's worktree updates in place. They jump to the session and type
"I pushed a CSS fix on top, carry on". Later, about to close the laptop, they
hand off a local grove branch to the mini and the new session shows up in the
list under mini.

## Constraints and decisions

Proposed, pending the author's review:

- Attention is derived from Crew's existing states and completions. No new
  session state, no polling of agents, and no scraping of terminal text such as
  the Claude TUI's "esc to interrupt" footer, which Morony's setup depends on.
- Observation stays passive. Collectors add only *where* a session's work is:
  machine, tty, tmux server and pane when it runs in tmux, and the checkout's
  branch, worktree and dirty state, all found from the harness's own process id
  and the checkout path at a slow cadence. The service stores seen marks.
  Neither ever sends anything to an agent, and no git hooks are added.
- Actions run on the MacBook using the author's own Ghostty scripting
  interface, SSH access, tmux and git. The mini service never carries input to
  agents or commits between machines, and gains no new privilege.
- Moving work uses git directly between the two Macs over SSH, with the mini as
  a remote named `mini` in each MacBook checkout. GitHub stays the shared origin
  and is not in this loop. The first operation on a project sets the remote up
  and asks once.
- The mini's repositories accept pushes into checked-out branches only when the
  worktree is clean (`receive.denyCurrentBranch updateInstead`). This was verified
  in a scratch repository on 2026-11-07, including a branch checked out in a
  linked worktree and the refusal when that worktree is dirty.
- Bring here is fast-forward only. Divergence is resolved by the author in a
  terminal; the list only reports it.
- The destination checkout for bring here is the project's clone on the MacBook
  that is not itself a worktree, unless the author configures another. Crew's
  existing project identity, one repository across clones and worktrees on both
  Macs, finds it.
- The author keeps working the way they do now: local sessions in Ghostty tabs
  and splits, mini sessions in tmux over SSH, worktrees under each project's
  convention such as memex's `.worktrees/<id>`.
- All three harnesses are covered by the list and by seen marks, because both
  derive from the common model. Jump and send cover any session with a terminal
  location; the three movement operations cover any session in a git checkout.
- The MacBook may sleep; the mini hosts the service as before. Freshness,
  staleness and outage behavior follow the activity specification. When the
  service is unreachable the list says so, keeps the last items with their age,
  and the shell commands keep working since they need only SSH and git.
- Seen marks and work locations are small metadata. Final responses and
  transcripts are not read or shown by this feature; the page's existing
  completion view already does that.

## Acceptance

- A permission prompt in a mini tmux window while the author works in a
  MacBook tab produces one MacBook notification within the activity
  specification's freshness target, and a *needs you* row naming mini, the
  project and the session title. Selecting the row focuses the Ghostty surface
  attached to the mini with that tmux window and pane selected.
- A request that finishes in an unfocused MacBook Ghostty tab produces one
  notification and a *finished* row. Focusing that tab clears the row on the
  MacBook and on the page and retracts the notification, with no key pressed in
  the list. A request that finishes in the focused, visible surface never alerts.
- Sending the next prompt in a session clears its item. Acknowledging from the
  phone page clears it on the MacBook and retracts the notification.
- An automatically approved permission check, readiness for the next prompt, an
  interrupted request and a replayed completion produce no item and no alert.
- A session without a terminal location is listed with its state and age and
  offers neither jump nor send.
- A stale machine's items show their age and raise no new alerts until fresh
  evidence arrives.
- Text sent from the list appears in the target terminal exactly as typed, once,
  and only that session receives it.
- A session in a git checkout shows its branch and worktree, and a change to the
  worktree's dirty state is reflected within the freshness target.
- Bring here on a mini session whose branch is new to the MacBook creates and
  checks out that branch at the mini's commit in the project's destination
  checkout; on a branch already there it fast-forwards. With uncommitted changes
  in the destination, or diverged branches, it changes nothing and states the
  reason. With uncommitted changes on the mini it brings the committed work and
  says what was left behind.
- Push back lands a MacBook commit in the mini worktree with the branch checked
  out there, and the next collector poll shows that worktree clean at the new
  commit. With uncommitted changes in that worktree, nothing changes on the mini
  and the list shows the refusal.
- Hand off to the mini leaves the branch on the mini, a worktree for it under the
  project's convention, a tmux window there, and a running Claude session that
  appears in the list under mini within the freshness target. The local session
  is untouched.
- Each movement operation's shell command produces the same result and the same
  refusals as the list action.
- Observation overhead is unchanged: no new hooks run inside agent callbacks,
  and terminal and work locations come from the collectors' existing poll.
- With the mini unreachable, the list says so, keeps the last known items with
  their age, and the MacBook's own sessions can still be jumped to.

## Open questions

Each with a recommendation from the discovery.

1. **Home.** Build this as a Crew increment, or as a separate project consuming
   Crew's API? Recommended: a Crew increment. Crew already owns the two-machine
   observation, the states this derives from, the project identity that maps a
   mini session to a MacBook checkout, the service that must hold seen marks,
   and the page the phone uses; a second repository would duplicate model types
   and deployment. The client can still be its own command.
2. **First version of reach.** Jump and seen only, or also send text?
   Recommended: include send text. Jump covers approvals and dialogs; send text
   covers the common "go ahead" and "I pushed a fix, carry on" replies without
   leaving the list.
3. **First version of movement.** Bring here and push back only, or hand off to
   the mini as well? Recommended: all three, provided hand off stays one action
   with the project's worktree convention supplied by configuration. Bring here
   and push back exist today as `mx` plus one git setting and can ship first.
4. **Form of the MacBook list.** A persistent sidebar in a Ghostty split, as the
   author pictures from crmux, or a popup opened on demand? Recommended: the
   sidebar, with the tmux window flags and status segment from the discovery as
   the zero-cost complement inside the mini's tmux.
5. **Local sessions.** Keep them in Ghostty tabs and splits, or move local work
   into tmux so one mechanism serves both Macs? Recommended: keep Ghostty.
   Ghostty 1.4's scripting interface reports each surface's tty and focuses it,
   so no change to the author's habits is needed.
6. **Notification style.** Standard banners, or persistent alerts as Morony
   achieves with a dedicated notifier bundle? Recommended: banners first, since
   retraction on seen and the sidebar already prevent silent loss.

## Out of scope

Answering approvals or dialogs by injected keystrokes; moving a conversation
between machines, which Claude Code does not support; merging, rebasing or
resetting on the author's behalf; continuous file synchronization between
checkouts, which the discovery considered and set aside; stopping sessions from
the list; phone push notifications beyond the page; reading transcripts or
responses in the list; Claude Code's own Remote Control and background-session
modes, which remain available alongside this; token or cost displays.

## Delivery

Five slices, each against the acceptance above; no structural prerequisite.
Slice 5 depends on none of the others and its shell form can ship first.

1. **Session location in observations.** Collectors report machine, tty and
   tmux server and pane for each session with a live process, and branch,
   worktree and dirty state for each session in a git checkout, from pid and
   checkout lookups in their existing poll. Model and API carry it; the page
   shows branch and dirty state.
2. **Attention and seen in the service.** Derive items from state and
   completions; store seen marks with their cause; accept focus evidence from
   collectors (tmux pane focus hooks on the mini, Ghostty focused-surface
   observation on the MacBook) and acknowledgements from clients.
3. **The MacBook list.** One command in a Ghostty split: ordered list,
   notifications with retraction, jump through Ghostty scripting and SSH plus
   tmux, send text, and the three movement actions calling slice 5. Handles the
   unreachable service.
4. **The page.** The attention list with acknowledgement, usable from the phone.
5. **Moving work.** Per-project remote setup and the mini-side push setting;
   bring here, push back and hand off as shell commands with the refusals above;
   the project's worktree convention and destination checkout as configuration.

Checks: `just check` as today; a bounded two-Mac live check of the first three
acceptance items and of bring here and push back against a scratch branch,
recorded as the activity effort did. Slice 1 has no visible behavior of its own
and can ship with slice 2.
