import { BalanceCard } from '../components/BalanceCard'
import { useBalance } from '../hooks/useBalance'

export function DashboardPanel({ merchantId }: { merchantId: string }) {
  const { balance, error } = useBalance(merchantId)

  if (error) return <p className="text-red-600 text-sm">{error}</p>
  if (!balance) return <p className="text-gray-400 text-sm">Loading balance…</p>

  return <BalanceCard balance={balance} />
}
