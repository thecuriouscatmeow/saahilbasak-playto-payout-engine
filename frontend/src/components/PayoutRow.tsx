import { StatusBadge } from './StatusBadge'
import { MoneyText } from './MoneyText'
import { formatRelative } from '../utils/formatTimestamp'
import type { Payout } from '../api/types'

export function PayoutRow({ payout }: { payout: Payout }) {
  return (
    <tr className="border-t border-gray-100">
      <td className="py-2 px-4 font-mono text-xs text-gray-500">{payout.id.slice(0, 8)}…</td>
      <td className="py-2 px-4"><MoneyText paise={payout.amount_paise} /></td>
      <td className="py-2 px-4"><StatusBadge status={payout.status} /></td>
      <td className="py-2 px-4 text-xs text-gray-500">{formatRelative(payout.created_at)}</td>
    </tr>
  )
}
