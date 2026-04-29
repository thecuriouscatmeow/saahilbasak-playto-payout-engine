import { fetchJson } from './client'
import type { Payout, PaginatedResponse } from './types'

export interface CreatePayoutRequest {
  amount_paise: number
  bank_account_id: string
}

export const createPayout = (data: CreatePayoutRequest) =>
  fetchJson<Payout>('/api/v1/payouts/', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const listPayouts = (merchantId: string) =>
  fetchJson<PaginatedResponse<Payout>>(`/api/v1/payouts/list/`)
