import { describe, expect, it } from 'vitest'
import { GatewayClientError } from '@/lib/api/errors'
import { getPhotoSearchFailureMessage } from '@/lib/api/errors'

describe('getPhotoSearchFailureMessage', () => {
  it('returns invalid-parameter copy for gateway 400 errors', () => {
    const error = new GatewayClientError(
      'image_source is required for face/style photo search',
      400,
      { error: { code: 'bad_request', message: 'image_source is required for face/style photo search' } },
    )

    expect(getPhotoSearchFailureMessage(error)).toBe(
      '这次发送的信息还不完整，你重新选张图，或者补一句你想找什么样的人。',
    )
  })

  it('returns busy copy for retryable gateway errors', () => {
    const error = new GatewayClientError(
      'photo search temporarily unavailable',
      503,
      {
        error: { code: 'photo_search_unavailable', message: 'photo search temporarily unavailable' },
        retryable: true,
      },
    )

    expect(getPhotoSearchFailureMessage(error)).toBe(
      '我这边刚刚有点忙，你稍等一下再试，我继续帮你找。',
    )
  })

  it('returns file-format copy for local image validation errors', () => {
    expect(getPhotoSearchFailureMessage(new Error('目前只支持 JPG、PNG、WEBP'))).toBe(
      '这张图片格式不对，换一张 JPG、PNG 或 WEBP 再试试。',
    )
  })
})
