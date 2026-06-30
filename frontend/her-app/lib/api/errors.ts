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

export function isAuthRequiredGatewayError(error: unknown): error is GatewayClientError {
  if (!(error instanceof GatewayClientError)) return false
  if (error.status === 401) return true
  if (error.status !== 403) return false
  const message = String(error.message || '').trim()
  return message.includes('请先登录')
}

export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (error instanceof GatewayClientError) {
    return error.message || fallback
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}
