import { describe, expect, it } from 'vitest'
import { countUnreadMessagesFromTimeline } from '@/lib/api/endpoints/chat'
import {
  formatConversionStageLabel,
  formatLedgerPhaseLabel,
  summarizeTimelineEvents,
} from '@/lib/api/endpoints/relations'

describe('relations helpers', () => {
  it('maps ledger phases to readable labels', () => {
    expect(formatLedgerPhaseLabel('chat_active')).toBe('聊天中')
    expect(formatLedgerPhaseLabel('case_active')).toBe('撮合进行中')
  })

  it('maps conversion stages to readable labels', () => {
    expect(formatConversionStageLabel('case_pending_contact')).toBe('待联系')
    expect(formatConversionStageLabel('review_queue')).toBe('待审核')
  })

  it('summarizes unified timeline events', () => {
    const items = summarizeTimelineEvents([
      { event_type: 'chat.message.created', occurred_at: '2026-05-01 10:00:00', source_service: 'chat' },
      { event_type: 'save', occurred_at: '2026-05-01 09:00:00', source_service: 'recommendation-system' },
    ])
    expect(items).toHaveLength(2)
    expect(items[0]?.content).toContain('消息')
  })

  it('counts unread main-group messages for the current participant', () => {
    const unread = countUnreadMessagesFromTimeline(
      {
        case_id: 'case-1',
        requester_id: 'user-b',
        conversation_count: 2,
        conversations: [
          {
            conversation: {
              conversation_id: 'conv-main',
              channel_key: 'main_group',
              conversation_kind: 'group',
            },
            messages: [
              { message_id: 1, author_id: 'user-b', body: 'hi', created_at: '2026-05-01 10:00:00' },
              { message_id: 2, author_id: 'user-a', body: 'hello', created_at: '2026-05-01 10:01:00' },
            ],
          },
          {
            conversation: {
              conversation_id: 'conv-dm',
              channel_key: 'assistant_dm_b',
              conversation_kind: 'dm',
            },
            messages: [
              { message_id: 3, author_id: 'agent-c', body: 'note', created_at: '2026-05-01 10:02:00' },
            ],
          },
        ],
      },
      'user-b',
    )
    expect(unread).toBe(1)
  })
})
