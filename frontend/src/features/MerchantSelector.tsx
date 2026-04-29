import { useState, useEffect } from 'react'
import { listMerchants } from '../api/merchantsApi'
import type { Merchant } from '../api/types'

interface Props {
  merchantId: string
  onSelect: (merchant: Merchant) => void
}

export function MerchantSelector({ merchantId, onSelect }: Props) {
  const [merchants, setMerchants] = useState<Merchant[]>([])

  useEffect(() => {
    listMerchants().then(setMerchants).catch(console.error)
  }, [])

  return (
    <div className="flex items-center gap-3">
      <label className="text-sm font-medium text-gray-700">Merchant</label>
      <select
        className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
        value={merchantId}
        onChange={(e) => {
          const found = merchants.find((m) => m.id === e.target.value)
          if (found) onSelect(found)
        }}
      >
        <option value="">— select —</option>
        {merchants.map((m) => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
      </select>
    </div>
  )
}
