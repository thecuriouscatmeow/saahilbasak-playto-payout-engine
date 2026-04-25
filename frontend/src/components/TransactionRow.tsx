import { MoneyText } from './MoneyText'
import { formatRelative } from '../utils/formatTimestamp'
import type { Transaction } from '../api/types'

const typeColour: Record<Transaction['type'], string> = {
  credit: 'bg-green-100 text-green-700',
  hold: 'bg-amber-100 text-amber-700',
  release: 'bg-blue-100 text-blue-700',
  debit: 'bg-red-100 text-red-700',
}

export function TransactionRow({ txn }: { txn: Transaction }) {
  return (
    <tr className="border-t border-gray-100">
      <td className="py-2 px-4">
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${typeColour[txn.type]}`}>
          {txn.type}
        </span>
      </td>
      <td className="py-2 px-4"><MoneyText paise={txn.amount_paise} /></td>
      <td className="py-2 px-4 text-xs text-gray-500">{formatRelative(txn.created_at)}</td>
    </tr>
  )
}
