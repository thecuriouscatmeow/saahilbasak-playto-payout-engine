import { useState, useEffect, useCallback } from 'react'
import { getBalance } from '../api/merchantsApi'
import type { Balance } from '../api/types'
import { usePolling } from './usePolling'

export function useBalance(merchantId: string) {
  const [balance, setBalance] = useState<Balance | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(() => {
    if (!merchantId) return
    getBalance(merchantId)
      .then((data) => { setBalance(data); setError(null) })
      .catch((e) => setError(e.message))
  }, [merchantId])

  useEffect(() => { fetch() }, [fetch])
  usePolling(fetch)

  return { balance, error, refetch: fetch }
}
