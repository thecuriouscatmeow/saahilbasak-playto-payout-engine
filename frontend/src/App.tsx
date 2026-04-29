import { useRef } from 'react'
import { MerchantSelector } from './features/MerchantSelector'
import { DashboardPanel } from './features/DashboardPanel'
import { PayoutForm } from './features/PayoutForm'
import { PayoutHistorySection } from './features/PayoutHistorySection'
import { TransactionLedger } from './features/TransactionLedger'
import { useMerchant } from './hooks/useMerchant'

export default function App() {
  const { merchantId, setMerchant } = useMerchant()
  const refetchBalanceRef = useRef<() => void>(() => {})
  const refetchPayoutsRef = useRef<() => void>(() => {})
  const refetchTransactionsRef = useRef<() => void>(() => {})

  const handlePayoutSuccess = () => {
    refetchBalanceRef.current()
    refetchPayoutsRef.current()
    refetchTransactionsRef.current()
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">
          Playto · <span className="text-gray-500 font-normal">Collected in USD · Paid out in INR</span>
        </h1>
        <MerchantSelector merchantId={merchantId} onSelect={setMerchant} />
      </header>

      {merchantId ? (
        <main className="max-w-5xl mx-auto px-6 py-8 flex flex-col gap-8">
          <DashboardPanel merchantId={merchantId} onRefetchReady={(fn) => { refetchBalanceRef.current = fn }} />
          <PayoutForm merchantId={merchantId} onSuccess={handlePayoutSuccess} />
          <PayoutHistorySection merchantId={merchantId} onRefetchReady={(fn) => { refetchPayoutsRef.current = fn }} />
          <TransactionLedger merchantId={merchantId} onRefetchReady={(fn) => { refetchTransactionsRef.current = fn }} />
        </main>
      ) : (
        <div className="flex items-center justify-center h-64 text-gray-400">
          Select a merchant to begin
        </div>
      )}
    </div>
  )
}
