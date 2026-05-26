import { gatewayJson, queryString } from '@/lib/api/client'
import type {
  CaseConversationTimelineResponse,
  CrossDomainTimelineResponse,
  LedgerSummary,
  UnifiedTimelineEvent,
} from '@/lib/types/relations'

const PHASE_LABELS: Record<string, string> = {
  new: '新推荐',
  recommended: '已推荐',
  case_active: '撮合进行中',
  chat_opened: '已开聊',
  chat_active: '聊天中',
  matched: '已匹配',
  proxy_intro_active: '代理牵线',
  direct_greet_started: '已打招呼',
  cooling: '冷却中',
  closed: '已结束',
}

const CONVERSION_STAGE_LABELS: Record<string, string> = {
  review_queue: '待审核',
  delivered: '已投递',
  case_requested: '待开案',
  case_handoff: '转撮合',
  case_closed: '案例结束',
  pending_contact: '待联系',
  pending_outreach: '待联系',
  awaiting_reply: '等待回复',
  accepted: '已接受',
}

export function formatLedgerPhaseLabel(phase?: string | null): string {
  if (!phase) return '关系进行中'
  return PHASE_LABELS[phase] || phase
}

export function formatConversionStageLabel(stage?: string | null): string {
  if (!stage) return ''
  const normalized = stage.replace(/^case_/, '')
  return CONVERSION_STAGE_LABELS[normalized] || CONVERSION_STAGE_LABELS[stage] || stage
}

export function summarizeTimelineEvents(events: UnifiedTimelineEvent[] | undefined, limit = 5) {
  if (!events?.length) return []
  return [...events]
    .sort((a, b) => String(a.occurred_at || '').localeCompare(String(b.occurred_at || '')))
    .slice(-limit)
    .reverse()
    .map((event, index) => ({
      id: `${event.event_type || 'event'}-${index}`,
      content: describeTimelineEvent(event),
      time: event.occurred_at || '刚刚',
      type: event.event_type?.includes('chat') ? 'greeting' as const : 'match' as const,
    }))
}

function describeTimelineEvent(event: UnifiedTimelineEvent): string {
  const service = event.source_service || event.source || 'system'
  const label = event.event_type || 'event'
  if (label.startsWith('chat.message')) return '会话里有新消息'
  if (label.includes('proxy_intro') || label.includes('case')) return `关系进度更新：${label}`
  if (label.includes('skip')) return '你跳过了推荐'
  if (label.includes('save')) return '你收藏了推荐'
  return `${service} · ${label}`
}

export async function fetchCaseConversationTimeline(
  caseId: string,
  requesterId: string,
  messageLimit = 50,
): Promise<CaseConversationTimelineResponse> {
  return gatewayJson<CaseConversationTimelineResponse>(
    `/v2/chat/cases/${caseId}/timeline${queryString({
      requester_id: requesterId,
      message_limit: messageLimit,
    })}`,
  )
}

export async function fetchCrossDomainTimeline(
  caseId: string,
  viewerId: string,
  messageLimit = 50,
): Promise<CrossDomainTimelineResponse> {
  return gatewayJson<CrossDomainTimelineResponse>(
    `/v1/timeline${queryString({
      case_id: caseId,
      viewer_id: viewerId,
      message_limit: messageLimit,
    })}`,
  )
}

export async function fetchRelationsMine(limit = 50) {
  return gatewayJson<{
    profile_ref: string
    relations: Array<Record<string, unknown>>
    count: number
    read_mode?: string
  }>(`/v1/relations/mine${queryString({ limit })}`)
}

export async function fetchRelationByCase(caseId: string) {
  return gatewayJson<{
    case_id: string
    relation: Record<string, unknown>
    summary: LedgerSummary
    unified_timeline: UnifiedTimelineEvent[]
  }>(`/v1/relations/by-case/${encodeURIComponent(caseId)}`)
}
