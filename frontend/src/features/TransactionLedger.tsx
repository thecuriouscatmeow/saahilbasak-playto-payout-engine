import { TableShell } from '../components/TableShell'
import { TransactionRow } from '../components/TransactionRow'
import { useTransactions } from '../hooks/useTransactions'

export function TransactionLedger({ merchantId }: { merchantId: string }) {
  const { transactions, error } = useTransactions(merchantId)

  return (
    <div>
      <h2 className="text-base font-semibold text-gray-900 mb-3">Transaction Ledger</h2>
      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}
      {transactions.length === 0 ? (
        <p className="text-gray-400 text-sm">No transactions yet.</p>
      ) : (
        <TableShell headers={['Type', 'Amount', 'Created']}>
          {transactions.map((t) => <TransactionRow key={t.id} txn={t} />)}
        </TableShell>
      )}
    </div>
  )
}
