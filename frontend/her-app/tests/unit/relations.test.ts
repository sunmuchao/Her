import { describe, expect, it } from 'vitest'
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
})
