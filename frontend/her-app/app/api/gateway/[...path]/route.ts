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

async function proxy(request: NextRequest, pathSegments: string[]) {
  const baseUrl = (process.env.PARTNER_GATEWAY_BASE_URL || 'http://127.0.0.1:8765').replace(/\/+$/, '')
  const upstreamUrl = `${baseUrl}/${pathSegments.join('/')}${request.nextUrl.search}`

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

  let body: string | undefined
  if (!['GET', 'HEAD'].includes(request.method.toUpperCase())) {
    body = await request.text()
  }

  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
    cache: 'no-store',
    redirect: 'manual',
  })

  const responseHeaders = new Headers()
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      responseHeaders.set(key, value)
    }
  })

  return new Response(await upstream.arrayBuffer(), {
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
