import { useState } from 'react'
import { createPayout, type CreatePayoutRequest } from '../api/payoutsApi'
import type { Payout } from '../api/types'
import { ApiError } from '../api/client'

interface CreatePayoutResult {
  submit: (data: CreatePayoutRequest) => Promise<void>
  loading: boolean
  error: string | null
  lastResult: Payout | null
}

export function useCreatePayout(onSuccess?: () => void): CreatePayoutResult {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<Payout | null>(null)

  const submit = async (data: CreatePayoutRequest) => {
    setLoading(true)
    setError(null)
    try {
      const payout = await createPayout(data)
      setLastResult(payout)
      onSuccess?.()
    } catch (e) {
      if (e instanceof ApiError) {
        const msg = e.body.error === 'insufficient_balance'
          ? `Insufficient balance (available: ₹${((e.body.available_paise ?? 0) / 100).toLocaleString('en-IN')})`
          : e.body.error ?? 'Unknown error'
        setError(msg)
      } else {
        setError('Network error')
      }
    } finally {
      setLoading(false)
    }
  }

  return { submit, loading, error, lastResult }
}
