import { fetchJson } from './client'
import type { Merchant, BankAccount, Balance, Transaction, PaginatedResponse } from './types'

export const listMerchants = () =>
  fetchJson<Merchant[]>('/api/v1/merchants/')

export const getBalance = (merchantId: string) =>
  fetchJson<Balance>(`/api/v1/merchants/${merchantId}/balance/`)

export const getTransactions = (merchantId: string) =>
  fetchJson<PaginatedResponse<Transaction>>(`/api/v1/merchants/${merchantId}/transactions/?limit=50`)

export const getBankAccounts = (merchantId: string) =>
  fetchJson<BankAccount[]>(`/api/v1/merchants/${merchantId}/bank_accounts/`)
