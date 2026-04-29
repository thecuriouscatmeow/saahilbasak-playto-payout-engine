import { useEffect } from 'react'
import { TableShell } from '../components/TableShell'
import { PayoutRow } from '../components/PayoutRow'
import { usePayouts } from '../hooks/usePayouts'

interface Props {
  merchantId: string
  onRefetchReady?: (fn: () => void) => void
}

export function PayoutHistorySection({ merchantId, onRefetchReady }: Props) {
  const { payouts, error, refetch } = usePayouts(merchantId)

  useEffect(() => { onRefetchReady?.(refetch) }, [refetch, onRefetchReady])

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-900 mb-3">Payout History</h2>
      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}
      {payouts.length === 0 ? (
        <p className="text-gray-400 text-sm">No payouts yet.</p>
      ) : (
        <TableShell headers={['ID', 'Amount', 'Status', 'Created']}>
          {payouts.map((p) => <PayoutRow key={p.id} payout={p} />)}
        </TableShell>
      )}
    </div>
  )
}
