export class GatewayClientError extends Error {
  status: number
  payload: unknown
  code?: string
  retryable?: boolean

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = 'GatewayClientError'
    this.status = status
    this.payload = payload
    if (payload && typeof payload === 'object') {
      const record = payload as { error?: { code?: string }; error_code?: string; retryable?: boolean }
      this.code = record?.error?.code || record?.error_code
      this.retryable = typeof record?.retryable === 'boolean' ? record.retryable : undefined
    }
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

function includesAny(text: string, patterns: string[]) {
  return patterns.some((pattern) => text.includes(pattern))
}

export function getPhotoSearchFailureMessage(error: unknown): string {
  if (isAuthRequiredGatewayError(error)) {
    return '我这边登录状态有点问题，你刷新一下页面，我再继续帮你找。'
  }

  if (error instanceof GatewayClientError) {
    const message = String(error.message || '').trim().toLowerCase()
    const code = String(error.code || '').trim().toLowerCase()

    if (
      error.status === 413 ||
      includesAny(message, ['10mb', 'too large', 'payload too large'])
    ) {
      return '这张图片有点大，你换一张 10MB 以内的再发我。'
    }

    if (
      error.status === 415 ||
      code === 'invalid_image_format' ||
      includesAny(message, ['jpg', 'png', 'webp', 'image format', 'image decode', 'unsupported image'])
    ) {
      return '这张图片格式我暂时认不出来，换一张 JPG、PNG 或 WEBP 再试试。'
    }

    if (
      error.status === 400 ||
      error.status === 422 ||
      includesAny(code, ['bad_request', 'invalid', 'missing']) ||
      includesAny(message, ['is required', 'must be one of', 'invalid'])
    ) {
      return '这次发送的信息还不完整，你重新选张图，或者补一句你想找什么样的人。'
    }

    if (
      error.retryable ||
      error.status >= 500 ||
      includesAny(code, ['photo_search_unavailable', 'profile_source_missing', 'gateway_unavailable']) ||
      includesAny(message, ['temporarily unavailable', 'timeout', 'busy'])
    ) {
      return '我这边刚刚有点忙，你稍等一下再试，我继续帮你找。'
    }
  }

  if (error instanceof Error) {
    const message = String(error.message || '').trim()
    if (message.includes('JPG') || message.includes('PNG') || message.includes('WEBP')) {
      return '这张图片格式不对，换一张 JPG、PNG 或 WEBP 再试试。'
    }
    if (message.includes('10MB')) {
      return '这张图片有点大，你换一张 10MB 以内的再发我。'
    }
  }

  return '这次我没处理好，你稍等一下再试，我继续帮你找。'
}
