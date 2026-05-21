import { getAccessToken, hasLinkedProfileIdentity } from '@/lib/auth/session'
import { GatewayClientError } from '@/lib/api/errors'

export { GatewayClientError, getErrorMessage, isGatewayClientError } from '@/lib/api/errors'

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
   * - default: attach only when login linked a profile (avoids requester_id vs actor mismatch in dev).
   */
  includeAuth?: boolean
}

function shouldAttachGatewayAuth(init?: GatewayRequestInit): boolean {
  if (init?.includeAuth === false) return false
  if (init?.includeAuth === true) return true
  return hasLinkedProfileIdentity()
}

function buildGatewayHeaders(init?: GatewayRequestInit) {
  const headers = new Headers(init?.headers || {})
  if (!headers.has('Content-Type') && init?.body) {
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
