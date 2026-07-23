import { afterEach, describe, expect, it, vi } from 'vitest'
import { submitDiscoveryTurn } from '@/lib/api/endpoints/discovery'

describe('submitDiscoveryTurn', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts unified multimodal payload to discovery turns endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ session: { session_id: 'session-1' }, view: { timeline: [] } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await submitDiscoveryTurn({
      sessionId: 'session-1',
      text: '帮我找像这张的',
      attachments: [
        { type: 'image', source: 'data:image/jpeg;base64,abc', mimeType: 'image/jpeg', role: 'reference' },
      ],
      clientContext: {
        entryPoint: 'discover_photo_composer',
      },
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/gateway/v1/discovery/turns')
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(JSON.parse(String(init.body))).toEqual({
      session_id: 'session-1',
      message: {
        text: '帮我找像这张的',
        attachments: [
          { type: 'image', source: 'data:image/jpeg;base64,abc', mimeType: 'image/jpeg', role: 'reference' },
        ],
      },
      client_context: {
        entryPoint: 'discover_photo_composer',
      },
    })
  })
})
