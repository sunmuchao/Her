import { gatewayJson } from '@/lib/api/client'
import type { DiscoverySessionResponse } from '@/lib/types/discovery'

export async function createDiscoverySession(params: { profileId: number }) {
  return gatewayJson<DiscoverySessionResponse>('/v1/discovery/sessions', {
    method: 'POST',
    body: JSON.stringify({
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
