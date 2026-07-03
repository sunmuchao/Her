import { gatewayJson, queryString } from '@/lib/api/client'

export type CallSession = {
  call_id?: string
  case_id?: string
  conversation_id?: string | null
  caller_id?: string
  callee_id?: string
  call_type?: 'audio' | 'video'
  status?: 'pending' | 'active' | 'ended'
  created_at?: string
  started_at?: string | null
  ended_at?: string | null
  end_reason?: string | null
}

export async function createCallSession(params: {
  caseId: string
  callerId: string
  calleeId: string
  callType: 'audio' | 'video'
  conversationId?: string | null
}) {
  return gatewayJson<{ call_session: CallSession; trace_id?: string }>('/v2/call/sessions', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      case_id: params.caseId,
      caller_id: params.callerId,
      callee_id: params.calleeId,
      call_type: params.callType,
      conversation_id: params.conversationId ?? undefined,
    }),
  })
}

export async function getCallSession(callId: string, requesterId: string) {
  return gatewayJson<{ call_session: CallSession; trace_id?: string }>(
    `/v2/call/sessions/${encodeURIComponent(callId)}${queryString({ requester_id: requesterId })}`,
    { includeAuth: true },
  )
}

export async function updateCallSessionStatus(params: {
  callId: string
  status: 'pending' | 'active' | 'ended'
  startedAt?: string
}) {
  return gatewayJson<{ call_session: CallSession; trace_id?: string }>(
    `/v2/call/sessions/${encodeURIComponent(params.callId)}/status`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        status: params.status,
        started_at: params.startedAt,
      }),
    },
  )
}

export async function endCallSession(params: {
  callId: string
  requesterId: string
  endReason?: string
}) {
  return gatewayJson<{ call_session: CallSession; trace_id?: string }>(
    `/v2/call/sessions/${encodeURIComponent(params.callId)}/end`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        requester_id: params.requesterId,
        end_reason: params.endReason ?? 'hangup',
      }),
    },
  )
}

export async function listCallSessionsByCase(caseId: string, requesterId: string, limit = 20) {
  return gatewayJson<{
    case_id: string
    requester_id: string
    call_count: number
    call_sessions: CallSession[]
    trace_id?: string
  }>(
    `/v2/call/cases/${encodeURIComponent(caseId)}/sessions${queryString({
      requester_id: requesterId,
      limit,
    })}`,
    { includeAuth: true },
  )
}
