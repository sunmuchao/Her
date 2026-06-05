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
  }>
  criteria_chips?: Array<{ label?: string }>
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
  session?: { session_id?: string }
  view?: DiscoveryView
}
