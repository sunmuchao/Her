import { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-length',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
])

function shouldLogVerificationProxy(upstreamPath: string) {
  return upstreamPath.startsWith('/v1/verifications/')
}

function getGatewayBaseUrls() {
  const configuredBaseUrl = process.env.PARTNER_GATEWAY_BASE_URL?.trim()
  if (configuredBaseUrl) {
    return [configuredBaseUrl.replace(/\/+$/, '')]
  }
  // Local fallback order:
  // 1. historical dev port 8765
  // 2. current docker/public gateway port 8080
  return ['http://127.0.0.1:8765', 'http://127.0.0.1:8080']
}

function upstreamUnavailableResponse(baseUrl: string, error: unknown) {
  const detail =
    error instanceof Error && error.message.trim()
      ? error.message.trim()
      : 'Unknown upstream fetch error'
  return Response.json(
    {
      error: {
        code: 'gateway_unavailable',
        message: `上游网关不可用，请确认 ${baseUrl} 已启动`,
        detail,
      },
    },
    { status: 502 },
  )
}

function misconfiguredGatewayResponse(baseUrl: string, upstreamUrl: string) {
  return Response.json(
    {
      error: {
        code: 'gateway_misconfigured',
        message: `上游地址 ${baseUrl} 不是 partner gateway，当前请求无法转发`,
        detail: `Expected partner-http-gateway route for ${upstreamUrl}`,
      },
    },
    { status: 502 },
  )
}

function isNotFoundPayloadFromAnotherService(
  upstreamPath: string,
  contentType: string | null,
  payloadText: string,
) {
  if (!upstreamPath.startsWith('/v1/')) return false
  if (!contentType?.toLowerCase().includes('application/json')) return false

  try {
    const payload = JSON.parse(payloadText) as { detail?: unknown; error?: unknown } | null
    return payload?.detail === 'Not Found' && !payload?.error
  } catch {
    return false
  }
}

function shouldRetryAgainstAnotherGatewayBase(
  upstreamPath: string,
  status: number,
  contentType: string | null,
  payloadText: string,
) {
  if (!upstreamPath.startsWith('/v1/')) return false

  const normalizedContentType = contentType?.toLowerCase() || ''
  const preview = payloadText.trim()

  if (status >= 300 && status < 400) {
    return true
  }

  if (
    normalizedContentType.startsWith('text/html') ||
    normalizedContentType.startsWith('application/xhtml+xml')
  ) {
    return true
  }

  if (
    normalizedContentType.startsWith('text/plain') &&
    (preview.includes('Failed to open a WebSocket connection') ||
      preview.includes('unsupported HTTP method') ||
      status >= 400)
  ) {
    return true
  }

  if (status === 404 && isNotFoundPayloadFromAnotherService(upstreamPath, contentType, payloadText)) {
    return true
  }

  return false
}

async function proxy(request: NextRequest, pathSegments: string[]) {
  const upstreamPath = `/${pathSegments.join('/')}`
  const logVerificationProxy = shouldLogVerificationProxy(upstreamPath)
  const gatewayBaseUrls = getGatewayBaseUrls()

  const headers = new Headers()
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value)
    }
  })

  const cookieToken = request.cookies.get('her_access_token')?.value?.trim()
  if (cookieToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${cookieToken}`)
  }

  const apiKey = (process.env.PARTNER_GATEWAY_API_KEY || '').trim()
  if (apiKey && !headers.has('Authorization') && !headers.has('X-API-Key')) {
    headers.set('Authorization', `Bearer ${apiKey}`)
  }

  let body: ArrayBuffer | string | undefined
  if (!['GET', 'HEAD'].includes(request.method.toUpperCase())) {
    // 检查 Content-Type，对二进制数据使用 arrayBuffer 保持原始格式
    const contentType = request.headers.get('content-type') || ''
    if (
      contentType.startsWith('audio/') ||
      contentType.startsWith('video/') ||
      contentType.startsWith('application/octet-stream') ||
      contentType.startsWith('multipart/') // multipart/form-data 也是二进制数据，不能用 text()
    ) {
      // 二进制数据：使用 arrayBuffer 保持原始格式
      body = await request.arrayBuffer()
    } else {
      // 文本数据：使用 text
      body = await request.text()
    }
  }

  if (logVerificationProxy) {
    console.info('[gateway-proxy] outgoing verification request', {
      method: request.method,
      contentType: request.headers.get('content-type'),
      contentLength: request.headers.get('content-length'),
      bodyKind:
        body instanceof ArrayBuffer ? 'arrayBuffer' : typeof body === 'string' ? 'text' : 'empty',
      bodyLength:
        body instanceof ArrayBuffer ? body.byteLength : typeof body === 'string' ? body.length : 0,
      hasAuthorization: headers.has('Authorization'),
      gatewayBaseUrls,
    })
  }
  let lastFetchError: unknown = null
  let lastMisconfiguredBaseUrl: string | null = null

  for (const baseUrl of gatewayBaseUrls) {
    const upstreamUrl = `${baseUrl}${upstreamPath}${request.nextUrl.search}`
    let upstream: Response
    try {
      upstream = await fetch(upstreamUrl, {
        method: request.method,
        headers,
        body,
        cache: 'no-store',
        redirect: 'manual',
      })
    } catch (error) {
      lastFetchError = error
      if (logVerificationProxy) {
        console.error('[gateway-proxy] verification upstream fetch failed', {
          upstreamUrl,
          error,
          message: error instanceof Error ? error.message : String(error),
        })
      }
      continue
    }

    const responseHeaders = new Headers()
    upstream.headers.forEach((value, key) => {
      if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
        responseHeaders.set(key, value)
      }
    })

    const responseBuffer = await upstream.arrayBuffer()
    const responseText =
      responseBuffer.byteLength > 0 ? new TextDecoder().decode(responseBuffer.slice(0, 4096)) : ''

    if (logVerificationProxy) {
      console.info('[gateway-proxy] verification upstream response', {
        upstreamUrl,
        status: upstream.status,
        statusText: upstream.statusText,
        contentType: upstream.headers.get('content-type'),
        responseBytes: responseBuffer.byteLength,
        responsePreview: responseText,
      })
    }

    if (
      gatewayBaseUrls.length > 1 &&
      shouldRetryAgainstAnotherGatewayBase(
        upstreamPath,
        upstream.status,
        upstream.headers.get('content-type'),
        responseText,
      )
    ) {
      lastMisconfiguredBaseUrl = baseUrl
      continue
    }

    return new Response(responseBuffer, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    })
  }

  if (lastMisconfiguredBaseUrl) {
    return misconfiguredGatewayResponse(lastMisconfiguredBaseUrl, `${lastMisconfiguredBaseUrl}${upstreamPath}${request.nextUrl.search}`)
  }

  return upstreamUnavailableResponse(gatewayBaseUrls[0], lastFetchError)
}

type RouteContext = {
  params: Promise<{ path: string[] }>
}

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  return proxy(request, path)
}

export async function HEAD(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  return proxy(request, path)
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  return proxy(request, path)
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  return proxy(request, path)
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  return proxy(request, path)
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params
  return proxy(request, path)
}
