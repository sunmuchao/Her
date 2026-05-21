import { afterEach, describe, expect, it, vi } from 'vitest'
import { GatewayClientError, gatewayJson } from '@/lib/api/client'

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
})
