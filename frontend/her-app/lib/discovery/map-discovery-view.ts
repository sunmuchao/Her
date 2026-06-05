import { formatRelativeTime } from '@/lib/format-relative-time'
import type { AssessmentResultCard } from '@/lib/api/endpoints/assessment'
import type { ValuesAuctionResultCard } from '@/lib/api/endpoints/valuesAuction'  // 新增：支持价值观拍卖会
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'
import type { CandidatePreview } from '@/lib/types/candidate'
import type { DiscoveryView } from '@/lib/types/discovery'

export type DiscoveryChatMessage = {
  id: string
  type: 'matchmaker' | 'user'
  content: string
  timestamp: string
}

export type DiscoveryResultGroupItem = {
  kind: 'result_group'
  id: string
  title?: string
  candidates: CandidatePreview[]
}

export type DiscoveryMessageItem = DiscoveryChatMessage & {
  kind: 'message'
}

export type DiscoveryProfileUpdatePromptItem = {
  kind: 'profile_update_prompt'
  id: string
  requestId: string
  title: string
  summary: string
  changes: Array<{
    field: string
    label: string
    from?: unknown
    to?: unknown
  }>
  status: 'pending' | 'confirmed' | 'rejected'
  timestamp?: string
}

export type DiscoveryAssessmentResultItem = {
  kind: 'assessment_result'
  id: string
  card: AssessmentResultCard | ValuesAuctionResultCard  // 新增：支持价值观拍卖会结果卡片
  timestamp?: string
}

export type DiscoverySuggestedActionsItem = {
  kind: 'suggested_actions'
  id: string
  actions: Array<{
    action_id: string
    label: string
    semantic_payload?: {
      kind: string
      assessment_type?: string
      [key: string]: unknown
    }
  }>
}

export type DiscoveryTimelineItem =
  | DiscoveryMessageItem
  | DiscoveryResultGroupItem
  | DiscoveryProfileUpdatePromptItem
  | DiscoveryAssessmentResultItem
  | DiscoverySuggestedActionsItem

export type MappedDiscoveryView = {
  /** Ordered chat stream: messages and result groups interleaved as returned by the API. */
  timelineItems: DiscoveryTimelineItem[]
  chips?: string[]
  actions: Array<{
    action_id: string
    label: string
    semantic_payload?: {
      kind: string
      assessment_type?: string
      [key: string]: unknown
    }
  }>
  composerPlaceholder: string
  composerDisabled: boolean
}

function mapDiscoveryCard(
  card: NonNullable<NonNullable<DiscoveryView['timeline']>[number]['cards']>[number],
): CandidatePreview | null {
  const id = String(card.profile_id || card.card_id || '').trim()
  if (!id) return null
  return {
    id,
    name: card.title || '候选人',
    city: card.subtitle || undefined,
    image: resolveProfileImageUrl(card.cover_image_url, PLACEHOLDER_AVATAR),
    matchScore: card.match_score,
    matchReason: card.personality_reasoning?.summary || card.reason_summary,
    personality_reasons: card.personality_reasons || card.personality_reasoning?.reasons,
    personality_reasoning: card.personality_reasoning,
    personality_bonus: card.personality_bonus,
    base_score: card.base_score,
    personality_scoring_trace: card.personality_scoring_trace,
    personality_match_context: card.personality_match_context,
  }
}

export function mapDiscoveryView(view?: DiscoveryView): MappedDiscoveryView {
  const timelineItems: DiscoveryTimelineItem[] = []

  for (const [index, item] of (view?.timeline || []).entries()) {
    const itemType = item.item_type || ''
    if (itemType === 'assistant_message' || itemType === 'user_message') {
      timelineItems.push({
        kind: 'message',
        id: item.item_id || `${itemType}-${index}`,
        type: itemType === 'user_message' ? 'user' : 'matchmaker',
        content: item.body || '',
        timestamp: formatRelativeTime(item.created_at),
      })
      continue
    }
    if (itemType === 'result_group') {
      const candidates = (item.cards || [])
        .map((card) => mapDiscoveryCard(card))
        .filter((candidate): candidate is CandidatePreview => candidate !== null)
      if (!candidates.length) continue
      timelineItems.push({
        kind: 'result_group',
        id: item.item_id || `result-group-${index}`,
        title: item.title,
        candidates,
      })
      continue
    }
    if (itemType === 'profile_update_prompt') {
      const prompt = item.prompt || {}
      const requestId = String(prompt.request_id || item.item_id || '').trim()
      if (!requestId) continue
      const rawStatus = String(prompt.status || 'pending').trim().toLowerCase()
      const status: DiscoveryProfileUpdatePromptItem['status'] =
        rawStatus === 'confirmed' || rawStatus === 'rejected' ? rawStatus : 'pending'
      timelineItems.push({
        kind: 'profile_update_prompt',
        id: item.item_id || requestId,
        requestId,
        title: String(prompt.title || '是否更新你的资料？'),
        summary: String(prompt.summary || ''),
        changes: (prompt.changes || []).map((change) => ({
          field: String(change.field || ''),
          label: String(change.label || change.field || ''),
          from: change.from,
          to: change.to,
        })),
        status,
        timestamp: formatRelativeTime(item.created_at),
      })
      continue
    }
    if (itemType === 'assessment_result' && item.card) {
      timelineItems.push({
        kind: 'assessment_result',
        id: item.item_id || `assessment-result-${index}`,
        card: item.card as AssessmentResultCard,
        timestamp: item.created_at ? formatRelativeTime(item.created_at) : undefined,
      })
    }
  }

  const chips = view?.criteria_chips?.map((item) => item.label).filter(Boolean) as string[] | undefined
  const actions =
    view?.suggested_actions
      ?.filter((item) => Boolean(item.action_id && item.label))
      .map((item) => ({
        action_id: item.action_id as string,
        label: item.label as string,
        semantic_payload: item.semantic_payload as { kind: string; assessment_type?: string; [key: string]: unknown } | undefined,
      })) || []

  if (actions.length) {
    timelineItems.push({
      kind: 'suggested_actions',
      id: 'suggested-actions',
      actions,
    })
  }

  return {
    timelineItems,
    chips,
    actions,
    composerPlaceholder: view?.composer?.placeholder || '输入你的想法...',
    composerDisabled: Boolean(view?.composer?.disabled),
  }
}

/** @deprecated Use timelineItems; kept for tests migrating from split messages/candidates. */
export function timelineHasCandidates(items: DiscoveryTimelineItem[]): boolean {
  return items.some((item) => item.kind === 'result_group' && item.candidates.length > 0)
}

/** Flat message list derived from timeline (e.g. optimistic append). */
export function extractMessagesFromTimeline(items: DiscoveryTimelineItem[]): DiscoveryChatMessage[] {
  return items.filter((item): item is DiscoveryMessageItem => item.kind === 'message')
}
