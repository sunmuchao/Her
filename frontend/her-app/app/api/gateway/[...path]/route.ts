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

async function proxy(request: NextRequest, pathSegments: string[]) {
  const baseUrl = (process.env.PARTNER_GATEWAY_BASE_URL || 'http://127.0.0.1:8765').replace(/\/+$/, '')
  const upstreamPath = `/${pathSegments.join('/')}`
  const upstreamUrl = `${baseUrl}${upstreamPath}${request.nextUrl.search}`

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
    // 检查 Content-Type，对音频/视频等二进制数据使用 arrayBuffer
    const contentType = request.headers.get('content-type') || ''
    if (contentType.startsWith('audio/') || contentType.startsWith('video/') || contentType.startsWith('application/octet-stream')) {
      // 二进制数据：使用 arrayBuffer 保持原始格式
      body = await request.arrayBuffer()
    } else {
      // 文本数据：使用 text
      body = await request.text()
    }
  }

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
    return upstreamUnavailableResponse(baseUrl, error)
  }

  const responseHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      responseHeaders.set(key, value)
    }
  })

  const responseBuffer = await upstream.arrayBuffer()
  if (upstream.status === 404) {
    const contentType = upstream.headers.get('content-type')
    const payloadText = new TextDecoder().decode(responseBuffer)
    if (isNotFoundPayloadFromAnotherService(upstreamPath, contentType, payloadText)) {
      return misconfiguredGatewayResponse(baseUrl, upstreamUrl)
    }
  }

  return new Response(responseBuffer, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

type RouteContext = {
  params: Promise<{ path: string[] }>
}

export async function GET(request: NextRequest, context: RouteContext) {
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
