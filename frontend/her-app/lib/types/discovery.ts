export type DiscoveryProfileUpdateChange = {
  field?: string
  label?: string
  from?: unknown
  to?: unknown
}

export type DiscoveryProfileUpdatePrompt = {
  request_id?: string
  title?: string
  summary?: string
  changes?: DiscoveryProfileUpdateChange[]
  status?: 'pending' | 'confirmed' | 'rejected'
}

export type DiscoveryView = {
  timeline?: Array<{
    item_type?: string
    item_id?: string
    body?: string
    title?: string
    created_at?: string
    prompt?: DiscoveryProfileUpdatePrompt
    card?: unknown
    cards?: Array<{
      card_id?: string
      profile_id?: string | number
      title?: string
      subtitle?: string
      cover_image_url?: string
      match_score?: number
      reason_summary?: string
      match_highlights?: string[]
      personality_reasons?: string[]
      personality_reasoning?: {
        used?: boolean
        source?: string
        signals?: string[]
        summary?: string
        reasons?: string[]
        confidence?: string
        score_components?: {
          values_bonus?: number
          attachment_bonus?: number
          temperament_bonus?: number
        }
      }
      personality_bonus?: number
      base_score?: number
      personality_scoring_trace?: {
        values_bonus?: number
        attachment_bonus?: number
        temperament_bonus?: number
        used_dimensions?: string[]
        attachment_reason?: string
        temperament_reason?: string
        shared_values?: string[]
        ranking_enabled?: boolean
        explanation_enabled?: boolean
        base_score?: number
      }
      personality_match_context?: {
        availability?: {
          has_values?: boolean
          has_attachment?: boolean
          has_mbti?: boolean
          has_big_five?: boolean
          has_sternberg?: boolean
          overall_completeness?: number
        }
        attachment?: {
          type_code?: string
          anxiety?: number
          avoidance?: number
        }
        mbti?: {
          type_code?: string
          scores?: Record<string, number>
        }
        big_five?: {
          scores?: Record<string, number>
        }
        values?: {
          value_type?: string
          top_values?: string[]
          tensions?: string[]
        }
        sternberg?: {
          type_code?: string
          scores?: Record<string, number>
        }
      }
      personality_availability?: {
        has_values?: boolean
        has_attachment?: boolean
        has_mbti?: boolean
        has_big_five?: boolean
        has_sternberg?: boolean
        overall_completeness?: number
      }
    }>
    // 新增：媒体metadata字段（用于语音播放）
    metadata?: {
      media_type?: 'image' | 'video' | 'audio'
      media_url?: string
      media_metadata?: {
        duration_ms?: number
        format?: string
        size?: number
        tts_engine?: string
        voice?: string
      }
    }
  }>
  criteria_chips?: Array<{ label?: string }>
  personality_trace?: {
    self_traits_available?: boolean
    candidate_traits_count?: number
    ranking_enabled?: boolean
    explanation_enabled?: boolean
    card_badges_enabled?: boolean
    top_candidates_used_personality?: number[]
    fallback_explanation_used?: boolean
  }
  suggested_actions?: Array<{
    action_id?: string
    label?: string
    semantic_payload?: {
      kind?: string
      assessment_type?: string
      [key: string]: unknown
    }
  }>
  composer?: { placeholder?: string; disabled?: boolean }
}

export type DiscoverySessionResponse = {
  session?: {
    session_id?: string
    status?: string
    phase?: string
    updated_at?: string
  }
  view?: DiscoveryView
}

export type DiscoverySessionSummary = {
  session_id?: string
  phase?: string
  status?: string
  created_at?: string
  updated_at?: string
  last_message_preview?: string
  candidate_count?: number
}

export type DiscoverySessionListResponse = {
  sessions?: DiscoverySessionSummary[]
  total?: number
}
