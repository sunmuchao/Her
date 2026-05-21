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

export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (error instanceof GatewayClientError) {
    return error.message || fallback
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function isGatewayClientError(error: unknown): error is GatewayClientError {
  return error instanceof GatewayClientError
}
