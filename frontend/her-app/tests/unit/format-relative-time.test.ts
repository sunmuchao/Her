import { describe, expect, it, vi } from 'vitest'
import { formatRelativeTime } from '@/lib/format-relative-time'
import { mapDiscoveryView } from '@/lib/discovery/map-discovery-view'

describe('formatRelativeTime', () => {
  it('returns 刚刚 for missing or invalid timestamps', () => {
    expect(formatRelativeTime(undefined)).toBe('刚刚')
    expect(formatRelativeTime('')).toBe('刚刚')
    expect(formatRelativeTime('not-a-date')).toBe('刚刚')
  })

  it('formats recent timestamps relatively', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-26T12:00:00+08:00'))
    expect(formatRelativeTime('2026-05-26T11:30:00+08:00')).toBe('30分钟前')
    vi.useRealTimers()
  })
})

describe('mapDiscoveryView', () => {
  it('maps timeline created_at to display timestamps', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-26T12:00:00+08:00'))
    const mapped = mapDiscoveryView({
      timeline: [
        {
          item_type: 'user_message',
          item_id: 'msg-u-1',
          body: '你好',
          created_at: '2026-05-26T11:45:00+08:00',
        },
      ],
    })
    expect(mapped.messages[0]?.timestamp).toBe('15分钟前')
    vi.useRealTimers()
  })
})
