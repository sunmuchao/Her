import { formatRelativeTime } from '@/lib/format-relative-time'
import type { CandidatePreview } from '@/lib/types/candidate'
import type { DiscoveryView } from '@/lib/types/discovery'

export type DiscoveryChatMessage = {
  id: string
  type: 'matchmaker' | 'user'
  content: string
  timestamp: string
}

export type MappedDiscoveryView = {
  messages: DiscoveryChatMessage[]
  chips?: string[]
  actions: Array<{ action_id: string; label: string }>
  candidates: CandidatePreview[]
  composerPlaceholder: string
  composerDisabled: boolean
}

export function mapDiscoveryView(view?: DiscoveryView): MappedDiscoveryView {
  const messages =
    view?.timeline
      ?.filter((item) => item.item_type === 'assistant_message' || item.item_type === 'user_message')
      .map((item, index) => ({
        id: item.item_id || String(index),
        type: item.item_type === 'user_message' ? ('user' as const) : ('matchmaker' as const),
        content: item.body || '',
        timestamp: formatRelativeTime(item.created_at),
      })) || []

  const chips = view?.criteria_chips?.map((item) => item.label).filter(Boolean) as string[] | undefined
  const actions =
    view?.suggested_actions
      ?.filter((item): item is { action_id: string; label: string } => Boolean(item.action_id && item.label))
      .map((item) => ({ action_id: item.action_id, label: item.label })) || []
  const candidates =
    view?.timeline
      ?.flatMap((item) => (item.item_type === 'result_group' ? item.cards || [] : []))
      .map((card) => ({
        id: String(card.profile_id || card.card_id || ''),
        name: card.title || '候选人',
        city: card.subtitle || undefined,
        image: card.cover_image_url,
        matchScore: card.match_score,
        matchReason: card.reason_summary,
      }))
      .filter((item) => item.id) || []

  return {
    messages,
    chips,
    actions,
    candidates,
    composerPlaceholder: view?.composer?.placeholder || '输入你的想法...',
    composerDisabled: Boolean(view?.composer?.disabled),
  }
}
