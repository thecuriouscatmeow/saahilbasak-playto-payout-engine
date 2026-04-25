import { MoneyText } from './MoneyText'
import type { Balance } from '../api/types'

export function BalanceCard({ balance }: { balance: Balance }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 flex gap-10">
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide">Available</p>
        <MoneyText paise={balance.available_paise} />
      </div>
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide">Held</p>
        <MoneyText paise={balance.held_paise} tone="muted" />
      </div>
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wide">Total Credits</p>
        <MoneyText paise={balance.total_credits_paise} tone="muted" />
      </div>
    </div>
  )
}
