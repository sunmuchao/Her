type LedgerSummary = {
  relation_key?: string
  relation_status?: string
  current_phase?: string
  recommendation_status_owner?: string
  case_progress_owner?: string | null
  case_progress_status?: string | null
  active_case_id?: string | null
  active_case_type?: string | null
  active_case_status?: string | null
  latest_chat_thread_id?: string | null
  event_count?: number
  case_count?: number
}

export type UnifiedTimelineEvent = {
  source?: string
  occurred_at?: string
  event_type?: string
  source_service?: string
  case_id?: string | null
  case_type?: string | null
  aggregate_type?: string
  aggregate_id?: string
  actor_type?: string
  actor_id?: string
}

export type CaseConversationTimelineResponse = {
  case_id: string
  requester_id: string
  conversation_count: number
  conversations: Array<{
    conversation: {
      conversation_id: string
      channel_key: string
      conversation_kind: string
      members?: Array<{
        participant_id: string
        member_role: string
      }>
    }
    messages: Array<{
      message_id: number
      author_id: string
      body: string
      created_at: string
    }>
  }>
  source_mode?: 'ledger_primary' | 'legacy_fallback'
  ledger_summary?: LedgerSummary | null
  unified_timeline?: UnifiedTimelineEvent[]
}

export type CrossDomainTimelineResponse = {
  case_id: string
  viewer_id: string
  source_mode?: 'ledger_primary' | 'legacy_fallback' | 'ledger_unavailable'
  unified_timeline?: UnifiedTimelineEvent[]
  ledger?: {
    summary?: LedgerSummary | null
    resolved_relation_key?: string
    read_mode?: string
  }
  chat?: CaseConversationTimelineResponse
}

export type ConversionView = {
  candidate_id?: number
  recommendation_id?: number
  recommendation_status?: string
  recommendation_phase?: string
  case_progress_status?: string | null
  conversion_stage?: string
  conversion_stage_owner?: string
  latest_case_id?: string | null
  latest_case_status?: string | null
  action_count?: number
  case_count?: number
}
