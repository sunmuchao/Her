import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NextRequest } from 'next/server'

const mockFetch = vi.fn<typeof fetch>()

describe('media proxy route', () => {
  beforeEach(() => {
    vi.resetModules()
    mockFetch.mockReset()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('proxies docker-internal minio audio requests and preserves range semantics', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response('partial-audio', {
        status: 206,
        headers: {
          'content-type': 'audio/mpeg',
          'content-length': '12',
          'accept-ranges': 'bytes',
          'content-range': 'bytes 0-11/42',
          etag: '"audio-etag"',
        },
      }),
    )

    const { GET } = await import('@/app/api/media-proxy/route')
    const request = new NextRequest(
      'http://localhost:3000/api/media-proxy?url=http://minio:9000/her-media/chat/demo.mp3',
      {
        headers: {
          range: 'bytes=0-11',
        },
      },
    )

    const response = await GET(request)

    expect(mockFetch).toHaveBeenCalledWith('http://minio:9000/her-media/chat/demo.mp3', {
      method: 'GET',
      cache: 'no-store',
      redirect: 'follow',
      headers: expect.any(Headers),
    })

    const forwardedHeaders = mockFetch.mock.calls[0]?.[1]?.headers
    expect(forwardedHeaders).toBeInstanceOf(Headers)
    expect((forwardedHeaders as Headers).get('range')).toBe('bytes=0-11')

    expect(response.status).toBe(206)
    expect(response.headers.get('content-type')).toBe('audio/mpeg')
    expect(response.headers.get('accept-ranges')).toBe('bytes')
    expect(response.headers.get('content-range')).toBe('bytes 0-11/42')
    expect(response.headers.get('etag')).toBe('"audio-etag"')
  })

  it('rejects non-allowlisted media hosts', async () => {
    const { GET } = await import('@/app/api/media-proxy/route')
    const request = new NextRequest(
      'http://localhost:3000/api/media-proxy?url=http://example.com/her-media/chat/demo.mp3',
    )

    const response = await GET(request)
    const payload = await response.json()

    expect(response.status).toBe(403)
    expect(payload.error.code).toBe('invalid_media_url')
    expect(mockFetch).not.toHaveBeenCalled()
  })
})
