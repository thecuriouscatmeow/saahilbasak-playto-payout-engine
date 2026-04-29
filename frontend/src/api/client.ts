import type { ApiErrorBody } from './types'

export class ApiError extends Error {
  status: number
  body: ApiErrorBody

  constructor(status: number, body: ApiErrorBody) {
    super(`API error ${status}: ${body.error ?? JSON.stringify(body)}`)
    this.status = status
    this.body = body
  }
}

let merchantApiKeyGetter: () => string = () => ''

export function setMerchantApiKeyGetter(fn: () => string) {
  merchantApiKeyGetter = fn
}

/** @deprecated use setMerchantApiKeyGetter */
export function setMerchantIdGetter(_fn: () => string) {
  // no-op: merchant identity is now derived from the API key
}

export async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }

  const apiKey = merchantApiKeyGetter()
  if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`

  if (init.method === 'POST' && !headers['Idempotency-Key']) {
    headers['Idempotency-Key'] = crypto.randomUUID()
  }

  const resp = await fetch(`${base}${path}`, { ...init, headers })
  const json = await resp.json()
  if (!resp.ok) throw new ApiError(resp.status, json as ApiErrorBody)
  return json as T
}
