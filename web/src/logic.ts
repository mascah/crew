// Pure view logic: grouping, filtering, relative time and avatar pixels.

import type { components } from './api'

type Schemas = components['schemas']
export type Snapshot = Schemas['Snapshot']
export type Session = Schemas['SessionView']
export type Machine = Schemas['MachineView']
export type Project = Schemas['ProjectView']
export type Completion = Schemas['CompletionSummary']
export type CompletionDetail = Schemas['CompletionDetail']
export type CompletionPage = Schemas['CompletionPage']
export type Harness = Session['harness']
export type State = Session['state']

export const DIMENSIONS = ['project', 'machine', 'harness'] as const
export type Dimension = (typeof DIMENSIONS)[number]
export type Filters = Partial<Record<Dimension, string>>
export type Group = { key: string; label: string; detail: string; sessions: Session[] }

export const HARNESS: Record<Harness, string> = {
  claude: 'Claude Code',
  codex: 'Codex CLI',
  hermes: 'Hermes Agent',
}

export const folderName = (path: string) => path.replace(/\/+$/, '').split('/').pop() || path

export const machineName = (snap: Snapshot, id: string) =>
  snap.machines.find((m) => m.id === id)?.name ?? id

/** Where a session belongs on each dimension. Without a project it belongs to
 * its checkout folder on its own Mac: the same path on the other Mac is
 * another folder. */
export function groupKey(s: Session, by: Dimension): string {
  if (by === 'machine') return s.machine_id
  if (by === 'harness') return s.harness
  return s.project_id ?? `folder:${s.machine_id}:${s.checkout ?? ''}`
}

/** Readable name for a group key, resolvable even when no session has it now
 * (a filter outlives the sessions it selected). */
export function describe(snap: Snapshot, by: Dimension, key: string) {
  if (by === 'machine') return { label: machineName(snap, key), detail: '' }
  if (by === 'harness') return { label: HARNESS[key as Harness] ?? key, detail: '' }
  const project = snap.projects.find((p) => p.id === key)
  if (project) return { label: project.name, detail: project.detail }
  const machine = snap.machines.find((m) => key.startsWith(`folder:${m.id}:`))
  const path = machine ? key.slice(`folder:${machine.id}:`.length) : ''
  return {
    label: path || 'No project or folder',
    detail: machine ? `folder on ${machine.name}` : '',
  }
}

/** Main sessions only: helpers stay nested under the parent that matched. */
export function filterSessions(sessions: Session[], filters: Filters): Session[] {
  return sessions.filter((s) =>
    DIMENSIONS.every((d) => !filters[d] || groupKey(s, d) === filters[d]),
  )
}

export function groupSessions(snap: Snapshot, sessions: Session[], by: Dimension): Group[] {
  const byKey = new Map<string, Session[]>()
  for (const s of sessions) {
    const key = groupKey(s, by)
    byKey.set(key, [...(byKey.get(key) ?? []), s])
  }
  return [...byKey]
    .map(([key, members]) => ({ key, ...describe(snap, by, key), sessions: members }))
    .sort((a, b) => a.label.localeCompare(b.label) || a.detail.localeCompare(b.detail))
}

/** Two projects called "crew" are two projects: a repeated name carries its
 * origin or folder wherever it is shown on its own. */
export function projectNames(projects: Project[]): Map<string, string> {
  const uses = new Map<string, number>()
  for (const p of projects) uses.set(p.name, (uses.get(p.name) ?? 0) + 1)
  return new Map(
    projects.map((p) => [p.id, uses.get(p.name)! > 1 ? `${p.name} (${p.detail})` : p.name]),
  )
}

export const countHelpers = (s: Session): number =>
  s.helpers.reduce((n, h) => n + 1 + countHelpers(h), 0)

/** Pages overlap when requests finish between fetches; ids keep each entry once.
 * A `newest` page sharing nothing with what is loaded means more finished than
 * one page holds while this tab was away: start again from it rather than leave
 * a hole that "Show more" could never fill. */
export function mergeCompletions(
  have: Completion[],
  got: Completion[],
  newest = false,
): Completion[] {
  if (newest && !got.some((c) => have.some((h) => h.id === c.id))) return got
  const byId = new Map([...have, ...got].map((c) => [c.id, c]))
  return [...byId.values()].sort((a, b) => b.completed_at - a.completed_at || b.id - a.id)
}

const relative = new Intl.RelativeTimeFormat('en', { style: 'narrow' })

/** "12s ago". Both times are epoch seconds from the service, so the browser's
 * clock never enters into it. */
export function ago(then: number, now: number): string {
  const s = Math.max(0, now - then) // a Mac's clock running ahead is not the future
  if (s < 2) return 'just now'
  if (s < 60) return relative.format(-Math.floor(s), 'second')
  if (s < 3600) return relative.format(-Math.floor(s / 60), 'minute')
  if (s < 86400) return relative.format(-Math.floor(s / 3600), 'hour')
  return relative.format(-Math.floor(s / 86400), 'day')
}

// FNV-1a with a murmur finaliser, so keys differing in one character still
// differ across all 32 bits.
function hash(text: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193)
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b)
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35)
  return (h ^ (h >>> 16)) >>> 0
}

/** An 8x8 sprite, mirrored left to right; true is a filled pixel. The key's
 * 32 hash bits fill the left half, while a fixed core with two eye holes keeps
 * every sprite a little creature rather than noise. */
export function avatarPixels(key: string): boolean[][] {
  const bits = hash(key)
  return Array.from({ length: 8 }, (_, y) =>
    Array.from({ length: 8 }, (_, x) => {
      const column = x < 4 ? x : 7 - x
      if (y === 3 && column === 2) return false // eye
      const core = y >= 2 && y <= 5 && column >= 2
      return core || ((bits >>> (y * 4 + column)) & 1) === 1
    }),
  )
}

/** Local wall-clock time for an epoch-seconds value. */
export const clock = (t: number) =>
  new Date(t * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
