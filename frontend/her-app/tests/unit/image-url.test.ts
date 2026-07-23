import { describe, expect, it } from 'vitest'

import {
  normalizeBrowserImageUrl,
  resolveProfileImageUrl,
  shouldBypassNextImageOptimization,
} from '@/lib/image-url'

describe('image-url helpers', () => {
  it('converts docker minio urls to browser-accessible urls', () => {
    expect(
      normalizeBrowserImageUrl(
        'http://minio:9000/her-media/virtual-profiles/local-wuxi-female/demo/avatar.jpg',
      ),
    ).toBe(
      'http://localhost:9000/her-media/virtual-profiles/local-wuxi-female/demo/avatar.jpg',
    )
  })

  it('keeps non-minio urls unchanged', () => {
    expect(resolveProfileImageUrl('https://images.unsplash.com/photo-demo')).toBe(
      'https://images.unsplash.com/photo-demo',
    )
  })

  it('bypasses next image optimization for local minio browser urls', () => {
    expect(
      shouldBypassNextImageOptimization(
        'http://localhost:9000/her-media/virtual-profiles/local-wuxi-female/demo/avatar.jpg',
      ),
    ).toBe(true)
  })
})
