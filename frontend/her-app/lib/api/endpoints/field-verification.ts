import { gatewayJson, queryString } from '@/lib/api/client'
import { getProfileId, getUserId } from '@/lib/auth/session'

export type FieldVerificationSubmission = {
  submission_id?: string
  field_key?: string
  status?: string
  profile_id?: number
}

const FIELD_KEY_MAP: Record<string, string> = {
  education: 'education',
  occupation: 'job',
  income: 'income',
}

function mapUiFieldToApiKey(fieldId: string): string {
  return FIELD_KEY_MAP[fieldId] || fieldId
}

export async function listFieldVerifications(profileId?: number): Promise<FieldVerificationSubmission[]> {
  const resolvedProfileId = profileId ?? getProfileId()
  if (!resolvedProfileId) return []

  const response = await gatewayJson<{ submissions?: FieldVerificationSubmission[] }>(
    `/v1/profile-verifications/submissions${queryString({
      profile_id: resolvedProfileId,
      limit: 20,
    })}`,
  )
  return response.submissions ?? []
}

export async function submitFieldVerification(params: {
  fieldId: string
  profileId?: number
  file?: File
  declaredValue?: string
}) {
  const profileId = params.profileId ?? getProfileId()
  const userId = getUserId()
  if (!profileId) throw new Error('缺少 profile_id')
  if (!userId) throw new Error('请先登录')

  let evidence: Record<string, unknown> | undefined
  if (params.file) {
    const base64 = await fileToBase64(params.file)
    evidence = {
      file_name: params.file.name,
      content_type: params.file.type || 'application/octet-stream',
      data_base64: base64,
    }
  }

  return gatewayJson<{ submission?: FieldVerificationSubmission }>(
    '/v1/profile-verifications/submissions',
    {
      method: 'POST',
      body: JSON.stringify({
        field_key: mapUiFieldToApiKey(params.fieldId),
        profile_id: profileId,
        subject_user_id: userId,
        declared_value: params.declaredValue,
        evidence,
        evidence_type: params.file ? 'document' : 'self_declared',
        evidence_channel: 'her-app',
      }),
    },
  )
}

async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}
