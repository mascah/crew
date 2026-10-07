import { expect, test } from 'vitest'
import {
  ago,
  avatarPixels,
  countHelpers,
  filterSessions,
  groupSessions,
  mergeCompletions,
  projectNames,
  type Completion,
  type Session,
  type Snapshot,
} from './logic'

function session(key: string, extra: Partial<Session> = {}): Session {
  const [machine_id = '', harness = '', session_id = ''] = key.split('/')
  return {
    key,
    machine_id,
    harness: harness as Session['harness'],
    session_id,
    state: 'working',
    activity: null,
    title: null,
    project_id: null,
    checkout: null,
    observed_at: 100,
    gap: null,
    helpers: [],
    ...extra,
  }
}

const nested = session('mini/codex/helper', { helpers: [session('mini/codex/grandchild')] })
const sessions = [
  session('mini/claude/a', { project_id: 'p1', checkout: '/Users/a/crew' }),
  session('book/claude/b', { project_id: 'p1', checkout: '/Users/a/src/crew' }),
  session('mini/codex/c', { project_id: 'p2', checkout: '/Users/a/old/crew', helpers: [nested] }),
  session('book/hermes/d', { checkout: '/Users/a/notes' }),
  session('mini/hermes/e', { checkout: '/Users/a/notes' }),
]
const snap: Snapshot = {
  server_time: 100,
  stale_after: 30,
  machines: [
    { id: 'book', name: 'Book', last_seen: 99, stale: false, adapters: [], expired_pending: 0 },
    { id: 'mini', name: 'Mini', last_seen: 99, stale: false, adapters: [], expired_pending: 0 },
  ],
  projects: [
    { id: 'p1', name: 'crew', detail: 'github.com/mascah/crew' },
    { id: 'p2', name: 'crew', detail: '/Users/a/old/crew' },
    { id: 'p3', name: 'office', detail: 'github.com/mascah/office' },
  ],
  sessions,
}
const keys = (list: Session[]) => list.map((s) => s.key)
const shape = (by: Parameters<typeof groupSessions>[2]) =>
  groupSessions(snap, sessions, by).map((g) => [g.label, g.detail, keys(g.sessions)])

test('groups by project: clones join, same-named projects and folders per Mac stay apart', () => {
  expect(shape('project')).toEqual([
    ['/Users/a/notes', 'folder on Book', ['book/hermes/d']],
    ['/Users/a/notes', 'folder on Mini', ['mini/hermes/e']],
    ['crew', '/Users/a/old/crew', ['mini/codex/c']],
    ['crew', 'github.com/mascah/crew', ['mini/claude/a', 'book/claude/b']],
  ])
})

test('groups by machine and by harness', () => {
  expect(shape('machine')).toEqual([
    ['Book', '', ['book/claude/b', 'book/hermes/d']],
    ['Mini', '', ['mini/claude/a', 'mini/codex/c', 'mini/hermes/e']],
  ])
  expect(shape('harness')).toEqual([
    ['Claude Code', '', ['mini/claude/a', 'book/claude/b']],
    ['Codex CLI', '', ['mini/codex/c']],
    ['Hermes Agent', '', ['book/hermes/d', 'mini/hermes/e']],
  ])
})

test('filters select a subset and combine', () => {
  expect(keys(filterSessions(sessions, {}))).toEqual(keys(sessions))
  expect(keys(filterSessions(sessions, { machine: 'book' }))).toEqual([
    'book/claude/b',
    'book/hermes/d',
  ])
  expect(keys(filterSessions(sessions, { harness: 'claude' }))).toEqual([
    'mini/claude/a',
    'book/claude/b',
  ])
  expect(keys(filterSessions(sessions, { project: 'p2' }))).toEqual(['mini/codex/c'])
  expect(keys(filterSessions(sessions, { project: 'folder:mini:/Users/a/notes' }))).toEqual([
    'mini/hermes/e',
  ])
  expect(keys(filterSessions(sessions, { machine: 'mini', harness: 'claude' }))).toEqual([
    'mini/claude/a',
  ])
  expect(filterSessions(sessions, { machine: 'book', harness: 'codex' })).toEqual([])
})

test('helpers stay nested under their parent through filtering and grouping', () => {
  const [group] = groupSessions(snap, filterSessions(sessions, { harness: 'codex' }), 'machine')
  const parent = group!.sessions[0]!
  expect(keys(parent.helpers)).toEqual(['mini/codex/helper'])
  expect(keys(parent.helpers[0]!.helpers)).toEqual(['mini/codex/grandchild'])
  expect(countHelpers(parent)).toBe(2)
  // Never promoted to a main session of their own.
  expect(keys(groupSessions(snap, sessions, 'harness').flatMap((g) => g.sessions))).not.toContain(
    'mini/codex/helper',
  )
})

test('a repeated project name carries its detail; a unique one does not', () => {
  const names = projectNames(snap.projects)
  expect(names.get('p1')).toBe('crew (github.com/mascah/crew)')
  expect(names.get('p2')).toBe('crew (/Users/a/old/crew)')
  expect(names.get('p3')).toBe('office')
})

test('relative time counts from the given now and never into the future', () => {
  expect(ago(88, 100)).toMatch(/^12 ?s(ec\.?)? ago$/)
  expect(ago(100 - 5 * 60 - 59, 100)).toMatch(/^5 ?m(in\.?)? ago$/)
  expect(ago(100 - 3 * 3600, 100)).toMatch(/^3 ?h(r\.?)? ago$/)
  expect(ago(100 - 2 * 86400, 100)).toMatch(/^2 ?d(ay)? ago$/)
  expect(ago(100, 100)).toBe('just now')
  expect(ago(160, 100)).toBe('just now')
})

test('avatars are deterministic, differ between sessions, and are symmetric', () => {
  const a = avatarPixels('mini/claude/a')
  expect(avatarPixels('mini/claude/a')).toEqual(a)
  expect(avatarPixels('mini/claude/b')).not.toEqual(a)
  expect(a).toHaveLength(8)
  for (const row of a) expect(row).toEqual([...row].reverse())
  // 200 sessions, 200 faces: collisions would make avatars useless as identity.
  const many = new Set(
    Array.from({ length: 200 }, (_, i) => JSON.stringify(avatarPixels(`mini/codex/${i}`))),
  )
  expect(many.size).toBe(200)
})

test('merging completion pages keeps each id once, newest first', () => {
  const c = (id: number, completed_at: number): Completion => ({
    id,
    completed_at,
    machine_id: 'mini',
    harness: 'claude',
    session_id: 's',
    project_id: null,
    title: null,
    excerpt: `v${completed_at}`,
  })
  // Thirty finished while the tab was hidden: no overlap, so no unreachable gap is kept.
  expect(mergeCompletions([c(3, 30), c(2, 20)], [c(40, 400), c(39, 390)], true)).toEqual([
    c(40, 400),
    c(39, 390),
  ])
  expect(mergeCompletions([c(3, 30)], [c(2, 20), c(1, 10)]).map((m) => m.id)).toEqual([3, 2, 1])
  const merged = mergeCompletions([c(3, 30), c(2, 20), c(1, 10)], [c(4, 40), c(3, 30), c(2, 25)])
  expect(merged.map((m) => [m.id, m.completed_at])).toEqual([
    [4, 40],
    [3, 30],
    [2, 25],
    [1, 10],
  ])
})
