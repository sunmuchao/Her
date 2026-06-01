import { afterEach, describe, expect, it, vi } from 'vitest'
import { GatewayClientError, gatewayJson } from '@/lib/api/client'
import { GET } from '@/app/api/gateway/[...path]/route'

describe('gatewayJson', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('throws GatewayClientError on non-json body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        text: async () => 'bad gateway',
      }),
    )

    await expect(gatewayJson('/v1/ping')).rejects.toBeInstanceOf(GatewayClientError)
  })

  it('parses error message from json payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () => JSON.stringify({ error: { message: '参数无效' } }),
      }),
    )

    await expect(gatewayJson('/v1/ping')).rejects.toMatchObject({
      message: '参数无效',
      status: 400,
    })
  })

  it('returns a structured 502 when upstream gateway is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('connect ECONNREFUSED 127.0.0.1:8765')))

    const request = {
      method: 'GET',
      headers: new Headers(),
      nextUrl: new URL('http://127.0.0.1:3000/api/gateway/v1/ping'),
      cookies: {
        get: vi.fn().mockReturnValue(undefined),
      },
    }

    const response = await GET(request as never, {
      params: Promise.resolve({ path: ['v1', 'ping'] }),
    })

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toMatchObject({
      error: {
        code: 'gateway_unavailable',
      },
    })
  })

  it('returns a structured 502 when upstream base url points to a different service', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Not Found' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    )

    const request = {
      method: 'GET',
      headers: new Headers(),
      nextUrl: new URL('http://127.0.0.1:3000/api/gateway/v1/auth/me'),
      cookies: {
        get: vi.fn().mockReturnValue(undefined),
      },
    }

    const response = await GET(request as never, {
      params: Promise.resolve({ path: ['v1', 'auth', 'me'] }),
    })

    expect(response.status).toBe(502)
    await expect(response.json()).resolves.toMatchObject({
      error: {
        code: 'gateway_misconfigured',
      },
    })
  })
})
