export class GatewayClientError extends Error {
  status: number
  payload: unknown

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = 'GatewayClientError'
    this.status = status
    this.payload = payload
  }
}

export function queryString(params: Record<string, string | number | boolean | undefined | null>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

function buildGatewayHeaders(init?: RequestInit) {
  const headers = new Headers(init?.headers || {})
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (typeof window !== 'undefined' && !headers.has('Authorization')) {
    const accessToken = window.localStorage.getItem('her_demo_access_token')
    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`)
    }
  }
  return headers
}

export async function gatewayJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/gateway${path}`, {
    ...init,
    headers: buildGatewayHeaders(init),
    cache: 'no-store',
  })

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null
  if (!response.ok) {
    const message =
      payload?.error?.message ||
      payload?.error_message ||
      `Gateway request failed with status ${response.status}`
    throw new GatewayClientError(message, response.status, payload)
  }
  return payload as T
}
