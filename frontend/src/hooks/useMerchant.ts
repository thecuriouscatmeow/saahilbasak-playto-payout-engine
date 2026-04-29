import { useState, useEffect } from 'react'
import { MERCHANT_STORAGE_KEY, MERCHANT_API_KEY_STORAGE_KEY } from '../utils/constants'
import { setMerchantApiKeyGetter } from '../api/client'
import type { Merchant } from '../api/types'

export function useMerchant() {
  const [merchantId, setMerchantId] = useState<string>(
    () => localStorage.getItem(MERCHANT_STORAGE_KEY) ?? ''
  )
  const [apiKey, setApiKey] = useState<string>(
    () => localStorage.getItem(MERCHANT_API_KEY_STORAGE_KEY) ?? ''
  )

  useEffect(() => {
    setMerchantApiKeyGetter(() => apiKey)
  }, [apiKey])

  const setMerchant = (merchant: Merchant | null) => {
    const id = merchant?.id ?? ''
    const key = merchant?.api_key ?? ''
    localStorage.setItem(MERCHANT_STORAGE_KEY, id)
    localStorage.setItem(MERCHANT_API_KEY_STORAGE_KEY, key)
    setMerchantId(id)
    setApiKey(key)
  }

  return { merchantId, setMerchant }
}
