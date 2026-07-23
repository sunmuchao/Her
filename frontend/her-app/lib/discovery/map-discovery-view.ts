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
  // 新增：媒体消息字段（用于语音播放）
  mediaType?: 'image' | 'video' | 'audio'
  mediaUrl?: string
  mediaMetadata?: {
    duration_ms?: number
    format?: string
    size?: number
    tts_engine?: string
    voice?: string
  }
  isNewMessage?: boolean  // 是否为新消息（用于自动播放语音，类似豆包）
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

export type DiscoveryAssessmentSuggestItem = {
  kind: 'assessment_suggest'
  id: string
  card: {
    card_type: string
    assessment_type: string
    title: string
    description: string
    duration?: string
    reward?: string
    action_label?: string
    action_id?: string
  }
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
  | DiscoveryAssessmentSuggestItem
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

function mapDiscoveryTimelineItem(
  item: NonNullable<DiscoveryView['timeline']>[number],
  index: number,
  now: Date,
): DiscoveryTimelineItem | null {
  const itemType = item.item_type || ''
  if (itemType === 'assistant_message' || itemType === 'user_message') {
    const createdAt = item.created_at ? new Date(item.created_at) : null
    const isNewMessage = createdAt
      ? (now.getTime() - createdAt.getTime()) < 10000
      : false

    return {
      kind: 'message',
      id: item.item_id || `${itemType}-${index}`,
      type: itemType === 'user_message' ? 'user' : 'matchmaker',
      content: item.body || '',
      timestamp: formatRelativeTime(item.created_at),
      mediaType: item.metadata?.media_type,
      mediaUrl: item.metadata?.media_url,
      mediaMetadata: item.metadata?.media_metadata,
      isNewMessage,
    }
  }
  if (itemType === 'result_group') {
    const candidates = (item.cards || [])
      .map((card) => mapDiscoveryCard(card))
      .filter((candidate): candidate is CandidatePreview => candidate !== null)
    if (!candidates.length) return null
    return {
      kind: 'result_group',
      id: item.item_id || `result-group-${index}`,
      title: item.title,
      candidates,
    }
  }
  if (itemType === 'profile_update_prompt') {
    const prompt = item.prompt || {}
    const requestId = String(prompt.request_id || item.item_id || '').trim()
    if (!requestId) return null
    const rawStatus = String(prompt.status || 'pending').trim().toLowerCase()
    const status: DiscoveryProfileUpdatePromptItem['status'] =
      rawStatus === 'confirmed' || rawStatus === 'rejected' ? rawStatus : 'pending'
    return {
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
    }
  }
  if (itemType === 'assessment_result' && item.card) {
    return {
      kind: 'assessment_result',
      id: item.item_id || `assessment-result-${index}`,
      card: item.card as AssessmentResultCard,
      timestamp: item.created_at ? formatRelativeTime(item.created_at) : undefined,
    }
  }
  if (itemType === 'assessment_suggest' && item.card) {
    return {
      kind: 'assessment_suggest',
      id: item.item_id || `assessment-suggest-${index}`,
      card: item.card as DiscoveryAssessmentSuggestItem['card'],
      timestamp: item.created_at ? formatRelativeTime(item.created_at) : undefined,
    }
  }
  return null
}

function mapDiscoveryCard(
  card: NonNullable<NonNullable<DiscoveryView['timeline']>[number]['cards']>[number],
): CandidatePreview | null {
  const id = String(card.profile_id || card.card_id || '').trim()
  if (!id) return null
  const fallbackTitle = card.title || '候选人'
  const titleParts = String(fallbackTitle).trim().split(/\s+/)
  const inferredName = titleParts[0] || '候选人'
  const subtitleParts = String(card.subtitle || '')
    .split('·')
    .map((part) => part.trim())
    .filter(Boolean)
  const normalizedAge = (() => {
    if (typeof card.age === 'number' && Number.isFinite(card.age)) return card.age
    const rawAge = String(card.age || '').trim()
    if (!/^\d{1,2}$/.test(rawAge)) return undefined
    const parsed = Number(rawAge)
    return Number.isFinite(parsed) ? parsed : undefined
  })()
  const inferredAge = (() => {
    const ageToken = titleParts.slice(1).find((part) => /^\d{1,2}$/.test(part))
    if (!ageToken) return undefined
    const parsed = Number(ageToken)
    return Number.isFinite(parsed) ? parsed : undefined
  })()
  return {
    id,
    name: inferredName,
    title: String(card.title || '').trim() || undefined,
    subtitle: String(card.subtitle || '').trim() || undefined,
    age: normalizedAge ?? inferredAge,
    city: card.city || subtitleParts[0] || undefined,
    occupation: card.occupation || subtitleParts[1] || undefined,
    education: card.education || subtitleParts[2] || undefined,
    verified: card.verified || undefined,
    image: resolveProfileImageUrl(card.cover_image_url, PLACEHOLDER_AVATAR),
    matchScore: card.match_score,
    matchReason: card.personality_reasoning?.summary || card.reason_summary,
    matchHighlights: card.match_highlights,
    personality_reasons: card.personality_reasons || card.personality_reasoning?.reasons,
    personality_reasoning: card.personality_reasoning,
    personality_bonus: card.personality_bonus,
    base_score: card.base_score,
    personality_scoring_trace: card.personality_scoring_trace,
    personality_match_context: card.personality_match_context as any,
    caseId: typeof card.case_id === 'string' ? card.case_id : undefined,
    viewType:
      card.view_type === 'interest' ||
      card.view_type === 'matched' ||
      card.view_type === 'delayed' ||
      card.view_type === 'candidate'
        ? card.view_type
        : undefined,
  }
}

export function mapDiscoveryView(view?: DiscoveryView): MappedDiscoveryView {
  const timelineItems: DiscoveryTimelineItem[] = []
  const now = new Date()

  for (const [index, item] of (view?.timeline || []).entries()) {
    const mappedItem = mapDiscoveryTimelineItem(item, index, now)
    if (mappedItem) timelineItems.push(mappedItem)
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
