import { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

const ALLOWED_HOSTS = new Set(['127.0.0.1', 'localhost', '0.0.0.0', 'minio'])
const ALLOWED_PORTS = new Set(['9000'])
const ALLOWED_PATH_PREFIXES = ['/her-media/']
const FORWARDED_REQUEST_HEADERS = [
  'range',
  'if-range',
  'if-none-match',
  'if-modified-since',
] as const
const FORWARDED_RESPONSE_HEADERS = [
  'content-type',
  'content-length',
  'accept-ranges',
  'content-range',
  'etag',
  'last-modified',
  'content-disposition',
] as const

function badRequest(message: string, status = 400) {
  return Response.json(
    {
      error: {
        code: 'invalid_media_url',
        message,
      },
    },
    { status },
  )
}

function isAllowedMediaUrl(url: URL) {
  if (!ALLOWED_HOSTS.has(url.hostname)) return false
  if (!ALLOWED_PORTS.has(url.port)) return false
  return ALLOWED_PATH_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))
}

function buildUpstreamHeaders(request: NextRequest) {
  const headers = new Headers()
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name)
    if (value) {
      headers.set(name, value)
    }
  }
  return headers
}

function buildResponseHeaders(upstream: Response) {
  const headers = new Headers()
  headers.set('Cache-Control', 'no-store')

  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name)
    if (value) {
      headers.set(name, value)
    }
  }

  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/octet-stream')
  }

  return headers
}

async function proxyMedia(request: NextRequest, method: 'GET' | 'HEAD') {
  const rawUrl = request.nextUrl.searchParams.get('url')?.trim()
  if (!rawUrl) {
    return badRequest('缺少 url 参数')
  }

  let mediaUrl: URL
  try {
    mediaUrl = new URL(rawUrl)
  } catch {
    return badRequest('url 参数不是合法地址')
  }

  if (!isAllowedMediaUrl(mediaUrl)) {
    return badRequest('不允许代理该媒体地址', 403)
  }

  let upstream: Response
  try {
    upstream = await fetch(mediaUrl.toString(), {
      method,
      cache: 'no-store',
      redirect: 'follow',
      headers: buildUpstreamHeaders(request),
    })
  } catch (error) {
    const detail =
      error instanceof Error && error.message.trim()
        ? error.message.trim()
        : 'unknown fetch error'
    return Response.json(
      {
        error: {
          code: 'media_fetch_failed',
          message: '媒体拉取失败',
          detail,
        },
      },
      { status: 502 },
    )
  }

  if (!upstream.ok) {
    return Response.json(
      {
        error: {
          code: 'media_upstream_error',
          message: `媒体源返回异常状态 ${upstream.status}`,
        },
      },
      { status: 502 },
    )
  }

  const headers = buildResponseHeaders(upstream)

  return new Response(upstream.body, {
    status: upstream.status,
    headers,
  })
}

export async function GET(request: NextRequest) {
  return proxyMedia(request, 'GET')
}

export async function HEAD(request: NextRequest) {
  return proxyMedia(request, 'HEAD')
}
