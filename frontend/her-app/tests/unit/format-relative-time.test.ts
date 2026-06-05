import { describe, expect, it, vi } from 'vitest'
import { formatRelativeTime } from '@/lib/format-relative-time'
import { mapDiscoveryView } from '@/lib/discovery/map-discovery-view'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'

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
    const message = mapped.timelineItems.find((item) => item.kind === 'message')
    expect(message && message.kind === 'message' ? message.timestamp : '').toBe('15分钟前')
    vi.useRealTimers()
  })

  it('preserves timeline order for messages and result groups', () => {
    const originalNodeEnv = process.env.NODE_ENV
    process.env.NODE_ENV = 'development'
    const mapped = mapDiscoveryView({
      timeline: [
        {
          item_type: 'assistant_message',
          item_id: 'msg-a-1',
          body: '先给你看几位。',
        },
        {
          item_type: 'result_group',
          item_id: 'group-1',
          title: '根据你的资料，先给你看这些',
          cards: [
            {
              profile_id: 1001,
              title: '林知夏 29',
              cover_image_url: 'https://cdn.her.local/1001.jpg',
              reason_summary: '城市一致',
              personality_match_context: {
                mbti: { type_code: 'INTJ' },
                attachment: { type_code: 'secure', anxiety: 22, avoidance: 18 },
                availability: {
                  has_mbti: true,
                  has_attachment: true,
                  overall_completeness: 0.4,
                },
              },
            },
          ],
        },
        {
          item_type: 'user_message',
          item_id: 'msg-u-1',
          body: '第二个不错',
        },
      ],
    })
    expect(mapped.timelineItems.map((item) => item.kind)).toEqual(['message', 'result_group', 'message'])
    const group = mapped.timelineItems[1]
    expect(group.kind === 'result_group' && group.candidates[0]?.id).toBe('1001')
    expect(group.kind === 'result_group' && group.candidates[0]?.image).toBe(PLACEHOLDER_AVATAR)
    expect(group.kind === 'result_group' && group.candidates[0]?.personality_match_context?.mbti?.type_code).toBe('INTJ')
    expect(group.kind === 'result_group' && group.candidates[0]?.personality_match_context?.attachment?.type_code).toBe('secure')
    process.env.NODE_ENV = originalNodeEnv
  })

  it('maps profile_update_prompt timeline items', () => {
    const mapped = mapDiscoveryView({
      timeline: [
        {
          item_type: 'profile_update_prompt',
          item_id: 'pur-1',
          prompt: {
            request_id: 'pur-req-1',
            title: '是否更新你的资料？',
            summary: '你提到搬到了杭州',
            changes: [{ field: 'city', label: '城市', from: '上海', to: '杭州' }],
            status: 'pending',
          },
        },
      ],
    })
    expect(mapped.timelineItems).toHaveLength(1)
    const prompt = mapped.timelineItems[0]
    expect(prompt.kind).toBe('profile_update_prompt')
    if (prompt.kind !== 'profile_update_prompt') return
    expect(prompt.requestId).toBe('pur-req-1')
    expect(prompt.changes[0]?.to).toBe('杭州')
    expect(prompt.status).toBe('pending')
  })

  it('maps assessment_result timeline items', () => {
    const mapped = mapDiscoveryView({
      timeline: [
        {
          item_type: 'assessment_result',
          item_id: 'assessment-1',
          created_at: '2026-05-26T11:45:00+08:00',
          card: {
            card_type: 'assessment_result',
            assessment_id: 'mbti_demo',
            result_data: {
              assessment_id: 'mbti_demo',
              type_code: 'INTJ',
              scores: { ei: 20, sn: 80, tf: 70, jp: 65 },
              dimension_rows: [],
              labels: ['理性'],
              reward: '测完了解你的恋爱优势与雷区',
            },
          },
        },
      ],
    })
    expect(mapped.timelineItems).toHaveLength(1)
    const result = mapped.timelineItems[0]
    expect(result.kind).toBe('assessment_result')
    if (result.kind !== 'assessment_result') return
    if (result.card.card_type !== 'assessment_result') return
    expect(result.card.result_data.type_code).toBe('INTJ')
  })
})
