import { useState } from 'react'
import { useEffect } from 'react'
import { getBankAccounts } from '../api/merchantsApi'
import type { BankAccount } from '../api/types'
import { useCreatePayout } from '../hooks/useCreatePayout'
import { FormField } from '../components/FormField'
import { Button } from '../components/Button'

interface Props {
  merchantId: string
  onSuccess: () => void
}

export function PayoutForm({ merchantId, onSuccess }: Props) {
  const [accounts, setAccounts] = useState<BankAccount[]>([])
  const [rupees, setRupees] = useState('')
  const [accountId, setAccountId] = useState('')
  const { submit, loading, error } = useCreatePayout(onSuccess)

  useEffect(() => {
    if (!merchantId) return
    getBankAccounts(merchantId).then(setAccounts).catch(console.error)
  }, [merchantId])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const paise = Math.round(parseFloat(rupees) * 100)
    if (!paise || !accountId) return
    submit({ amount_paise: paise, bank_account_id: accountId })
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-6 flex flex-col gap-4">
      <h2 className="text-base font-semibold text-gray-900">New Payout</h2>

      <FormField label="Amount (₹)">
        <input
          type="number"
          min="0.01"
          step="0.01"
          placeholder="e.g. 500.00"
          value={rupees}
          onChange={(e) => setRupees(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
        />
      </FormField>

      <FormField label="Bank Account">
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          required
        >
          <option value="">— select account —</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.label} ({a.account_number})</option>
          ))}
        </select>
      </FormField>

      {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}

      <Button type="submit" disabled={loading}>
        {loading ? 'Submitting…' : 'Submit Payout'}
      </Button>
    </form>
  )
}
