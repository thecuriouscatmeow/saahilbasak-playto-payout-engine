export interface Merchant {
  id: string
  name: string
}

export interface BankAccount {
  id: string
  ifsc: string
  account_number: string
  label: string
  is_active: boolean
}

export interface Balance {
  available_paise: number
  held_paise: number
  total_credits_paise: number
}

export interface Transaction {
  id: string
  type: 'credit' | 'hold' | 'release' | 'debit'
  amount_paise: number
  payout_id: string | null
  created_at: string
}

export interface Payout {
  id: string
  merchant_id: string
  bank_account_id: string
  amount_paise: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string
  updated_at: string
}

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface ApiErrorBody {
  error: string
  available_paise?: number
  requested_paise?: number
  [key: string]: unknown
}
