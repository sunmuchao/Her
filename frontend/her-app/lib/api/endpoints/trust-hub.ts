import { gatewayJson, queryString } from '@/lib/api/client'
import type { TrustHubPayload } from '@/lib/trust/map-trust-hub'

export type TrustHubResponse = {
  trust_hub: TrustHubPayload & {
    risk_records?: {
      items?: Array<{
        title?: string
        description?: string
        time?: string
        status?: string
      }>
    }
    notifications?: Array<{
      title?: string
      body?: string
      created_at?: string
    }>
  }
}

export async function fetchTrustHub(params: { userId: string; profileId?: number }) {
  return gatewayJson<TrustHubResponse>(
    `/v1/user-center/trust-hub${queryString({
      user_id: params.userId,
      profile_id: params.profileId,
    })}`,
  )
}
