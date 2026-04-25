import { useState, useEffect, useCallback } from 'react'
import { getTransactions } from '../api/merchantsApi'
import type { Transaction } from '../api/types'

export function useTransactions(merchantId: string) {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    if (!merchantId) return
    getTransactions(merchantId)
      .then((r) => setTransactions(r.results))
      .catch((e) => setError(e.message))
  }, [merchantId])

  useEffect(() => { refetch() }, [refetch])

  return { transactions, error, refetch }
}
