import { useState, useEffect } from 'react'
import { MERCHANT_STORAGE_KEY } from '../utils/constants'
import { setMerchantIdGetter } from '../api/client'

export function useMerchant() {
  const [merchantId, setMerchantIdState] = useState<string>(
    () => localStorage.getItem(MERCHANT_STORAGE_KEY) ?? ''
  )

  useEffect(() => {
    setMerchantIdGetter(() => merchantId)
  }, [merchantId])

  const setMerchantId = (id: string) => {
    localStorage.setItem(MERCHANT_STORAGE_KEY, id)
    setMerchantIdState(id)
  }

  return { merchantId, setMerchantId }
}
