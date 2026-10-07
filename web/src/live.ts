// Reading the service: one fetch helper and one visibility-aware poll.

import { useEffect, useRef } from 'react'

export class HttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`)
  }
}

export async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  // A hung connection has to fail, or the page would go on claiming to be live.
  // (A plain controller: AbortSignal.any is missing on older tablets and phones.)
  const request = new AbortController()
  const cancel = () => request.abort()
  const timer = setTimeout(cancel, 5000)
  signal.addEventListener('abort', cancel, { once: true })
  if (signal.aborted) cancel()
  try {
    // Relative, like the built assets, so the page works wherever it is mounted.
    const response = await fetch(`api/${path}`, { cache: 'no-store', signal: request.signal })
    if (!response.ok) throw new HttpError(response.status)
    return await response.json()
  } finally {
    clearTimeout(timer)
    signal.removeEventListener('abort', cancel)
  }
}

/** Runs `run` now and then `ms` after each run finishes, while the tab is
 * visible. Hiding the tab aborts the request in flight and calls `onPause`;
 * showing it again runs immediately. `run` handles its own errors and should
 * ignore an outcome whose signal was aborted. */
export function usePoll(
  run: (signal: AbortSignal) => Promise<void>,
  ms: number,
  onPause?: () => void,
) {
  const latest = useRef({ run, onPause })
  latest.current = { run, onPause }
  useEffect(() => {
    let abort: AbortController | undefined
    let timer: number | undefined
    const stop = () => {
      abort?.abort()
      clearTimeout(timer)
    }
    const start = () => {
      stop()
      const { signal } = (abort = new AbortController())
      const loop = async () => {
        await latest.current.run(signal)
        if (!signal.aborted) timer = setTimeout(loop, ms)
      }
      void loop()
    }
    const onVisibility = () => {
      if (!document.hidden) return start()
      stop()
      latest.current.onPause?.()
    }
    document.addEventListener('visibilitychange', onVisibility)
    if (!document.hidden) start()
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      stop()
    }
  }, [ms])
}
