import { afterEach, describe, expect, it, vi } from 'vitest'
import { GatewayClientError } from '@/lib/api/errors'

vi.mock('@/lib/api/client', () => ({
  gatewayJson: vi.fn(),
}))

import { gatewayJson } from '@/lib/api/client'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'

describe('fetchMyProxyIntroCases', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('treats 404 as an empty list', async () => {
    vi.mocked(gatewayJson).mockRejectedValue(new GatewayClientError('请求失败（404）', 404, null))

    await expect(fetchMyProxyIntroCases()).resolves.toEqual({ cases: [], count: 0 })
  })
})
