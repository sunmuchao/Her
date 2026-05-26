import { gatewayJson } from '@/lib/api/client'

export type TrustSummary = {
  profile_id?: number
  verified_level?: string | null
  labels?: string[]
  field_verifications?: Record<string, string>
  verified_label?: string | null
  photo_verification_label?: string | null
  headline?: string | null
}

export async function fetchProfileTrust(profileId: string | number) {
  return gatewayJson<{ profile_id: number; trust_summary: TrustSummary }>(
    `/v1/profiles/${encodeURIComponent(String(profileId))}/trust`
  )
}
