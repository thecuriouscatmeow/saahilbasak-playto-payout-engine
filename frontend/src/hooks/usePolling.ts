import { useEffect, useRef } from 'react'
import { POLL_INTERVAL_MS } from '../utils/constants'

export function usePolling(fn: () => void, intervalMs = POLL_INTERVAL_MS) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    const tick = () => {
      if (!document.hidden) fnRef.current()
    }

    const id = setInterval(tick, intervalMs)
    const onVisible = () => { if (!document.hidden) fnRef.current() }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [intervalMs])
}
