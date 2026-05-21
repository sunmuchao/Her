import { gatewayJson } from '@/lib/api/client'
import { queryString } from '@/lib/api/client'
import type { DiscoveryProfileDetailResponse, DiscoverySessionResponse } from '@/lib/types/discovery'

export async function createDiscoverySession(params: {
  requesterId: number
  profileId: number
}) {
  return gatewayJson<DiscoverySessionResponse>('/v1/discovery/sessions', {
    method: 'POST',
    body: JSON.stringify({
      requester_id: params.requesterId,
      profile_id: params.profileId,
    }),
  })
}

export async function submitDiscoveryTurn(params: {
  sessionId: string
  userMessage?: string
  actionId?: string
}) {
  return gatewayJson<DiscoverySessionResponse>(
    `/v1/discovery/sessions/${params.sessionId}/turns`,
    {
      method: 'POST',
      body: JSON.stringify(
        params.actionId
          ? { action_id: params.actionId }
          : { user_message: params.userMessage },
      ),
    },
  )
}

export async function fetchDiscoveryProfileDetail(params: {
  profileId: string | number
  sessionId?: string | null
}) {
  return gatewayJson<DiscoveryProfileDetailResponse>(
    `/v1/discovery/profiles/${params.profileId}${queryString({
      session_id: params.sessionId,
    })}`,
    { method: 'GET' },
  )
}
