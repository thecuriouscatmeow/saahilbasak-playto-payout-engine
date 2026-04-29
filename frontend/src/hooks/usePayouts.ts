import { useState, useEffect, useCallback } from 'react'
import { listPayouts } from '../api/payoutsApi'
import type { Payout } from '../api/types'
import { usePolling } from './usePolling'

export function usePayouts(merchantId: string) {
  const [payouts, setPayouts] = useState<Payout[]>([])
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!merchantId) return
    listPayouts(merchantId)
      .then((r) => { setPayouts(r.results); setError(null) })
      .catch((e) => setError(e.message))
  }, [merchantId])

  useEffect(() => { fetch() }, [fetch])
  usePolling(fetch)

  return { payouts, error, refetch: fetch }
}
