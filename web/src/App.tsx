import { memo, useId, useState } from 'react'
import { Finished } from './Finished'
import { get, HttpError, usePoll } from './live'
import {
  ago,
  avatarPixels,
  clock,
  countHelpers,
  describe,
  DIMENSIONS,
  filterSessions,
  folderName,
  groupSessions,
  HARNESS,
  machineName,
  projectNames,
  type Dimension,
  type Filters,
  type Machine,
  type Session,
  type Snapshot,
  type State,
} from './logic'

const STATE: Record<State, string> = {
  working: 'Working',
  waiting: 'Waiting for you',
  idle: 'Idle',
  unknown: 'Unknown', // an observation gap, never shown as idle
}
const DIMENSION: Record<Dimension, string> = {
  project: 'Project',
  machine: 'Machine',
  harness: 'Harness',
}
const ALL: Record<Dimension, string> = {
  project: 'All projects',
  machine: 'All machines',
  harness: 'All harnesses',
}

export function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [link, setLink] = useState<'loading' | 'live' | 'lost' | 'forbidden'>('loading')
  usePoll(
    async (signal) => {
      try {
        setSnap(await get<Snapshot>('snapshot', signal))
        setLink('live')
      } catch (error) {
        if (signal.aborted) return
        setLink(error instanceof HttpError && error.status === 403 ? 'forbidden' : 'lost')
      }
    },
    2000,
    // A tab coming back has to fetch before what it kept counts as live again.
    () => setLink((was) => (was === 'live' ? 'lost' : was)),
  )

  if (link === 'forbidden')
    return (
      <main className="page">
        <header className="top">
          <h1>Crew</h1>
        </header>
        <p>This page is limited to the configured Tailscale account.</p>
      </main>
    )

  const live = link === 'live'
  const names = projectNames(snap?.projects ?? [])
  return (
    <div className="page">
      <header className="top">
        <h1>Crew</h1>
        <p className={`link ${link}`} role="status">
          {live
            ? 'Live'
            : snap
              ? `Reconnecting… showing data from ${clock(snap.server_time)}`
              : link === 'lost'
                ? 'Cannot reach Crew. Retrying…'
                : 'Loading current activity…'}
        </p>
        {snap && <a href="#finished">Recently finished requests</a>}
      </header>
      {snap && (
        <main className="columns">
          <Machines snap={snap} live={live} />
          <Activity snap={snap} live={live} names={names} />
          <Finished snap={snap} names={names} />
        </main>
      )}
    </div>
  )
}

const staleNote = (m: Machine, now: number) => `Not reporting — last seen ${ago(m.last_seen, now)}`

function problems(m: Machine): string[] {
  const lost = m.expired_pending
  return [
    ...m.adapters.flatMap((a) => [
      ...(a.ok ? [] : [`${HARNESS[a.harness]} cannot be observed: ${a.error ?? 'no reason reported'}`]),
      ...a.gaps.map((gap) => `${HARNESS[a.harness]}: ${gap}`),
    ]),
    ...(lost > 0
      ? [
          `${lost} finished ${lost === 1 ? 'request was' : 'requests were'} lost while this Mac could not report`,
        ]
      : []),
  ]
}

function Machines({ snap, live }: { snap: Snapshot; live: boolean }) {
  return (
    <section className="machines" aria-labelledby="machines-heading">
      <h2 id="machines-heading">Machines</h2>
      {snap.machines.length === 0 && <p className="quiet">No Mac has reported yet.</p>}
      <ul>
        {snap.machines.map((m) => (
          <li key={m.id} className={m.stale ? 'stale' : undefined}>
            <strong>{m.name}</strong>{' '}
            <span>
              {m.stale ? staleNote(m, snap.server_time) : live ? 'Reporting' : 'Was reporting'}
            </span>
            {problems(m).length > 0 && (
              <ul className="problems">
                {problems(m).map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

type View = {
  snap: Snapshot
  live: boolean
  names: Map<string, string>
  expanded: ReadonlySet<string>
  toggle: (key: string) => void
}

function Activity({ snap, live, names }: Pick<View, 'snap' | 'live' | 'names'>) {
  const [by, setBy] = useState<Dimension>('project')
  const [filters, setFilters] = useState<Filters>({})
  // Keyed by session key, so it outlives every refresh of the data.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const toggle = (key: string) =>
    setExpanded((was) => {
      const next = new Set(was)
      if (!next.delete(key)) next.add(key)
      return next
    })
  const view: View = { snap, live, names, expanded, toggle }

  const optionLabel = (d: Dimension, key: string) => {
    const { label, detail } = describe(snap, d, key)
    return names.get(key) ?? (detail ? `${label} (${detail})` : label)
  }
  const options = (d: Dimension) => {
    const keys =
      d === 'machine'
        ? snap.machines.map((m) => m.id)
        : d === 'harness'
          ? Object.keys(HARNESS)
          : groupSessions(snap, snap.sessions, 'project').map((g) => g.key)
    // A selection whose sessions have gone still has to be visible to clear.
    const selected = filters[d]
    return selected && !keys.includes(selected) ? [...keys, selected] : keys
  }
  const shown = filterSessions(snap.sessions, filters)
  const active = DIMENSIONS.filter((d) => filters[d])
  const total = snap.sessions.length

  return (
    <section aria-labelledby="activity-heading">
      <h2 id="activity-heading">Current activity</h2>
      <div className="controls">
        <label>
          Group by
          <select value={by} onChange={(e) => setBy(e.target.value as Dimension)}>
            {DIMENSIONS.map((d) => (
              <option key={d} value={d}>
                {DIMENSION[d]}
              </option>
            ))}
          </select>
        </label>
        {DIMENSIONS.map((d) => (
          <label key={d}>
            {DIMENSION[d]}
            <select
              className={filters[d] ? 'on' : undefined}
              value={filters[d] ?? ''}
              onChange={(e) => setFilters({ ...filters, [d]: e.target.value || undefined })}
            >
              <option value="">{ALL[d]}</option>
              {options(d).map((key) => (
                <option key={key} value={key}>
                  {optionLabel(d, key)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <p className="showing">
        {active.length === 0
          ? `${total} ${total === 1 ? 'session' : 'sessions'}`
          : `Showing ${shown.length} of ${total} sessions for`}
        {active.map((d) => (
          <button
            key={d}
            className="chip"
            aria-label={`Clear ${DIMENSION[d].toLowerCase()} filter: ${optionLabel(d, filters[d]!)}`}
            onClick={() => setFilters({ ...filters, [d]: undefined })}
          >
            {DIMENSION[d]}: {optionLabel(d, filters[d]!)} <span aria-hidden="true">×</span>
          </button>
        ))}
      </p>
      {shown.length === 0 && (
        <p className="quiet">
          {total === 0
            ? 'No sessions are reported right now.'
            : 'No sessions match these filters right now.'}
        </p>
      )}
      {groupSessions(snap, shown, by).map((g) => {
        const machine = by === 'machine' ? snap.machines.find((m) => m.id === g.key) : undefined
        const detail = machine?.stale ? staleNote(machine, snap.server_time) : g.detail
        return (
          <section key={g.key} className="group">
            <h3>
              <span>{g.label}</span>
              {detail && <small>{detail}</small>}
            </h3>
            <ul className="sessions">
              {g.sessions.map((s) => (
                <Row key={s.key} s={s} view={view} depth={0} />
              ))}
            </ul>
          </section>
        )
      })}
    </section>
  )
}

function Row({ s, view, depth }: { s: Session; view: View; depth: number }) {
  const { snap, names } = view
  const helpersId = useId()
  // A stale Mac's sessions, and anything kept from before a failed fetch, are
  // last observations rather than confirmed current activity.
  const last = !view.live || snap.machines.find((m) => m.id === s.machine_id)?.stale
  const title = s.title ?? (s.checkout ? folderName(s.checkout) : 'Untitled session')
  const helpers = countHelpers(s)
  const open = depth > 0 || view.expanded.has(s.key)
  const meta =
    depth > 0
      ? [] // a helper runs on its parent's Mac and harness
      : [
          s.project_id ? (names.get(s.project_id) ?? 'Unknown project') : !s.checkout && 'No project',
          machineName(snap, s.machine_id),
          HARNESS[s.harness],
          s.checkout,
        ]

  return (
    <li className={`session ${s.harness} ${last ? 'last' : s.state}`}>
      <Avatar seed={s.key} />
      <div className="body">
        <p className="head">
          <span className="title">{title}</span>
          <span className={`state ${last ? 'last' : s.state}`}>
            {last ? `last observed: ${STATE[s.state].toLowerCase()}` : STATE[s.state]}
          </span>
        </p>
        {s.activity && <p className="doing">{s.activity}</p>}
        <p className="meta">
          {[...meta, `updated ${ago(s.observed_at, snap.server_time)}`].map(
            (text, i) => text && <span key={i}>{text}</span>,
          )}
        </p>
        {s.gap && <p className="gap">Not observed: {s.gap}</p>}
        {depth === 0 && helpers > 0 && (
          <button
            className="toggle"
            aria-expanded={open}
            aria-controls={helpersId}
            onClick={() => view.toggle(s.key)}
          >
            {helpers} {helpers === 1 ? 'helper' : 'helpers'}
          </button>
        )}
        {open && helpers > 0 && (
          <ul className="sessions helpers" id={helpersId}>
            {s.helpers.map((h) => (
              <Row key={h.key} s={h} view={view} depth={depth + 1} />
            ))}
          </ul>
        )}
      </div>
    </li>
  )
}

// Decorative: the labels beside it carry state, harness and identity.
const Avatar = memo(function Avatar({ seed }: { seed: string }) {
  const d = avatarPixels(seed)
    .flatMap((row, y) => row.flatMap((on, x) => (on ? [`M${x} ${y}h1v1h-1z`] : [])))
    .join('')
  return (
    <svg className="avatar" viewBox="0 0 8 8" shapeRendering="crispEdges" aria-hidden="true">
      <path d={d} />
    </svg>
  )
})
