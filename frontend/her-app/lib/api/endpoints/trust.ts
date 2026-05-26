export type TrustSummary = {
  profile_id?: number
  verified_level?: string | null
  labels?: string[]
  field_verifications?: Record<string, string>
  verified_label?: string | null
  photo_verification_label?: string | null
  headline?: string | null
}
