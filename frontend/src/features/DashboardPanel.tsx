import { useEffect } from 'react'
import { BalanceCard } from '../components/BalanceCard'
import { useBalance } from '../hooks/useBalance'

interface Props {
  merchantId: string
  onRefetchReady?: (fn: () => void) => void
}

export function DashboardPanel({ merchantId, onRefetchReady }: Props) {
  const { balance, error, refetch } = useBalance(merchantId)

  useEffect(() => { onRefetchReady?.(refetch) }, [refetch, onRefetchReady])

  if (error) return <p className="text-red-600 text-sm">{error}</p>
  if (!balance) return <p className="text-gray-400 text-sm">Loading balance…</p>

  return <BalanceCard balance={balance} />
}
