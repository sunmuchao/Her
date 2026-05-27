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
    cards?: Array<{
      card_id?: string
      profile_id?: string | number
      title?: string
      subtitle?: string
      cover_image_url?: string
      match_score?: number
      reason_summary?: string
    }>
  }>
  criteria_chips?: Array<{ label?: string }>
  suggested_actions?: Array<{ action_id?: string; label?: string }>
  composer?: { placeholder?: string; disabled?: boolean }
}

export type DiscoverySessionResponse = {
  session?: { session_id?: string }
  view?: DiscoveryView
}
