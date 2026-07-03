import { getAccessToken } from '@/lib/auth/session'
import { GatewayClientError } from '@/lib/api/errors'

export { GatewayClientError } from '@/lib/api/errors'

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

export type GatewayRequestInit = RequestInit & {
  /**
   * - `true`: always attach Bearer when token exists (e.g. /v1/auth/me).
   * - `false`: never attach (pre-login auth calls).
   * - default: attach Bearer when a login access token exists.
   */
  includeAuth?: boolean
  /**
   * AbortSignal for cancelling the request
   */
  signal?: AbortSignal
}

function shouldAttachGatewayAuth(init?: GatewayRequestInit): boolean {
  if (init?.includeAuth === false) return false
  if (init?.includeAuth === true) return true
  return Boolean(getAccessToken())
}

function shouldDefaultJsonContentType(body: BodyInit | null | undefined) {
  if (!body) return false
  if (typeof FormData !== 'undefined' && body instanceof FormData) return false
  if (typeof Blob !== 'undefined' && body instanceof Blob) return false
  if (typeof ArrayBuffer !== 'undefined' && body instanceof ArrayBuffer) return false
  if (typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams) return false
  return true
}

function buildGatewayHeaders(init?: GatewayRequestInit) {
  const headers = new Headers(init?.headers || {})
  if (!headers.has('Content-Type') && shouldDefaultJsonContentType(init?.body)) {
    headers.set('Content-Type', 'application/json')
  }
  const shouldAttachAuth = shouldAttachGatewayAuth(init)
  if (shouldAttachAuth && typeof window !== 'undefined' && !headers.has('Authorization')) {
    const accessToken = getAccessToken()
    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`)
    }
  }
  return headers
}

export async function gatewayJson<T>(path: string, init?: GatewayRequestInit): Promise<T> {
  const response = await fetch(`/api/gateway${path}`, {
    ...init,
    headers: buildGatewayHeaders(init),
    credentials: 'include',
    cache: 'no-store',
    signal: init?.signal, // Support request cancellation
  })

  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      throw new GatewayClientError('服务器返回了无效的数据格式', response.status, text)
    }
  }

  if (!response.ok) {
    const record = payload as { error?: { message?: string }; error_message?: string } | null
    const message =
      record?.error?.message ||
      record?.error_message ||
      `请求失败（${response.status}）`
    throw new GatewayClientError(message, response.status, payload)
  }

  return payload as T
}
