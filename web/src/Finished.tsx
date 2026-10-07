// The secondary view: requests agents finished, each with its final response.
// "Finished" means the agent settled its latest request. It says nothing about
// whether the work was right or whether the session is still open.

import { useEffect, useRef, useState } from 'react'
import { get, HttpError, usePoll } from './live'
import {
  ago,
  clock,
  HARNESS,
  machineName,
  mergeCompletions,
  type Completion,
  type CompletionDetail,
  type CompletionPage,
  type Snapshot,
} from './logic'

const PAGE = 20

type Props = { snap: Snapshot; names: Map<string, string> }

const projectOf = (c: Completion, names: Props['names']) =>
  c.project_id ? (names.get(c.project_id) ?? 'Unknown project') : 'No project'

const titleOf = (c: Completion, names: Props['names']) =>
  c.title ?? (c.project_id && names.get(c.project_id)) ?? 'Untitled request'

export function Finished({ snap, names }: Props) {
  const [items, setItems] = useState<Completion[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [reading, setReading] = useState<Completion | null>(null)

  const load = async (offset: number, signal: AbortSignal) => {
    try {
      const page = await get<CompletionPage>(`completions?limit=${PAGE}&offset=${offset}`, signal)
      setItems((was) => mergeCompletions(was, page.items, offset === 0))
      setTotal(page.total)
      setFailed(false)
    } catch {
      if (!signal.aborted) setFailed(true)
    }
  }
  // Only the newest page is refetched; older pages already loaded stay.
  usePoll((signal) => load(0, signal), 10_000)

  const more = async () => {
    setBusy(true)
    await load(items.length, new AbortController().signal)
    setBusy(false)
  }

  return (
    <section className="finished" id="finished" aria-labelledby="finished-heading">
      <h2 id="finished-heading">Recently finished requests</h2>
      <p className="quiet">
        Requests an agent finished responding to. Open one to read its final response.
      </p>
      {failed && (
        <p className="quiet" role="status">
          {items.length > 0
            ? 'Could not refresh this list; showing what was loaded earlier.'
            : 'Could not load finished requests. Retrying…'}
        </p>
      )}
      {total === 0 && <p className="quiet">No finished requests are retained yet.</p>}
      <ol className="requests">
        {items.map((c) => (
          <li key={c.id}>
            <h3>
              <button onClick={() => setReading(c)}>{titleOf(c, names)}</button>
            </h3>
            <p className="meta">
              <span>Request finished {ago(c.completed_at, snap.server_time)}</span>
              <span>{projectOf(c, names)}</span>
              <span>{machineName(snap, c.machine_id)}</span>
              <span>{HARNESS[c.harness]}</span>
            </p>
            <p className="excerpt">{c.excerpt}</p>
          </li>
        ))}
      </ol>
      {total !== null && items.length < total && (
        <button className="more" disabled={busy} onClick={more}>
          {busy ? 'Loading…' : `Show more (${items.length} of ${total} shown)`}
        </button>
      )}
      {reading && (
        <Response item={reading} snap={snap} names={names} onClose={() => setReading(null)} />
      )}
    </section>
  )
}

function Response({ item, snap, names, onClose }: Props & { item: Completion; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [detail, setDetail] = useState<CompletionDetail | 'gone' | 'failed' | null>(null)

  useEffect(() => {
    // Native modal: focus moves in, Escape closes, focus returns to the entry.
    if (!dialog.current?.open) dialog.current?.showModal()
    const abort = new AbortController()
    get<CompletionDetail>(`completions/${item.id}`, abort.signal).then(setDetail, (error) => {
      if (abort.signal.aborted) return
      setDetail(error instanceof HttpError && error.status === 404 ? 'gone' : 'failed')
    })
    return () => abort.abort()
  }, [item.id])

  return (
    <dialog
      ref={dialog}
      aria-labelledby="response-title"
      onClose={onClose}
      // The dialog element itself is only exposed as its backdrop.
      onClick={(e) => e.target === e.currentTarget && e.currentTarget.close()}
    >
      <div className="sheet">
        <header>
          <h2 id="response-title">{titleOf(item, names)}</h2>
          <button onClick={() => dialog.current?.close()}>Close</button>
        </header>
        <p className="meta">
          <span>Request finished {clock(item.completed_at)}</span>
          <span>{projectOf(item, names)}</span>
          <span>{machineName(snap, item.machine_id)}</span>
          <span>{HARNESS[item.harness]}</span>
        </p>
        {detail === null && <p className="quiet">Loading the final response…</p>}
        {detail === 'gone' && <p className="quiet">This finished request is no longer retained.</p>}
        {detail === 'failed' && (
          <p className="quiet">Could not load the final response. Close this and open it again.</p>
        )}
        {detail && typeof detail === 'object' && (
          <pre tabIndex={0} aria-label="Final response">
            {detail.response || 'The final response was empty.'}
          </pre>
        )}
      </div>
    </dialog>
  )
}
