import { gatewayJson, queryString } from '@/lib/api/client'
import { getProfileId } from '@/lib/auth/session'

export type ProfileFactsResponse = {
  profile_id: number
  profile_facts: Record<string, unknown>
  photos?: string[]  // 后端返回的照片 URL 列表
  access_method?: string  // 后端返回的访问方式
}

export type CollectedStatementsResponse = {
  user_key: string
  collected_statements: Record<string, unknown>
  collected_items?: Record<
    string,
    {
      value: unknown
      source_channel?: string
      collected_at?: string
      evidence?: string
      source_type?: string
    }
  >
}

const COLLECTED_FIELD_LABELS: Record<string, string> = {
  target_age_min: '年龄下限',
  target_age_max: '年龄上限',
  target_cities: '城市',
  target_height_min: '身高下限',
  target_height_max: '身高上限',
  target_education_min: '学历',
  target_gender: '性别',
  target_marital_statuses: '婚况',
  target_accept_partner_children: '对方孩子',
  target_accept_long_distance: '异地',
  must_have_tags: '必须有',
  must_not_have_tags: '不接受',
  preferred_traits: '偏好特质',
  disliked_traits: '不喜欢',
}

const DISPLAYABLE_COLLECTED_FIELDS = new Set(Object.keys(COLLECTED_FIELD_LABELS))

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.map(String).join('、')
  return String(value)
}

export function formatCollectedPreferenceChips(statements: Record<string, unknown>): string[] {
  const chips: string[] = []
  const ageMin = statements.target_age_min
  const ageMax = statements.target_age_max
  if (ageMin != null || ageMax != null) {
    if (ageMin != null && ageMax != null) {
      chips.push(`年龄 ${ageMin}-${ageMax}`)
    } else if (ageMin != null) {
      chips.push(`年龄 ≥ ${ageMin}`)
    } else {
      chips.push(`年龄 ≤ ${ageMax}`)
    }
  }

  for (const [key, value] of Object.entries(statements)) {
    if (key === 'target_age_min' || key === 'target_age_max') continue
    if (!DISPLAYABLE_COLLECTED_FIELDS.has(key)) continue
    const text = formatValue(value)
    if (!text) continue
    const label = COLLECTED_FIELD_LABELS[key]
    chips.push(`${label} ${text}`)
  }
  return chips
}

export function mapCollectedToPreferenceGrid(statements: Record<string, unknown>): Record<string, string> {
  const ageMin = statements.target_age_min
  const ageMax = statements.target_age_max
  const ageRange =
    ageMin != null && ageMax != null
      ? `${ageMin}-${ageMax}岁`
      : ageMin != null
        ? `${ageMin}岁以上`
        : ageMax != null
          ? `${ageMax}岁以下`
          : '待设置'

  return {
    ageRange,
    location: formatValue(statements.target_cities) || '待设置',
    education: formatValue(statements.target_education_min) || '待设置',
    height:
      statements.target_height_min != null || statements.target_height_max != null
        ? `${formatValue(statements.target_height_min) || '?'} - ${formatValue(statements.target_height_max) || '?'} cm`
        : '待设置',
  }
}

export async function fetchProfileFacts(): Promise<ProfileFactsResponse> {
  // /v1/profile/me 只返回当前用户的资料，不接受 profile_id 参数
  // 这是安全设计：防止 IDOR 攻击（通过修改参数偷看别人资料）
  const response = await gatewayJson<ProfileFactsResponse>(
    '/v1/profile/me',
    { includeAuth: true },
  )
  console.log('[fetchProfileFacts] 后端返回数据:', {
    profile_id: response.profile_id,
    has_photos: 'photos' in response,
    photos: response.photos,
    photos_length: response.photos?.length,
    profile_facts_keys: Object.keys(response.profile_facts || {}),
  })
  return response
}

export async function fetchCollectedStatements(profileId?: number): Promise<CollectedStatementsResponse> {
  const id = profileId ?? getProfileId()
  return gatewayJson<CollectedStatementsResponse>(
    `/v1/persona/collected${queryString({ profile_id: id ?? undefined })}`,
    { includeAuth: true },
  )
}

export function formatExplainSourceMap(sourceMap: Record<string, string>): string[] {
  return Object.entries(sourceMap || {}).map(([key, source]) => {
    const label = COLLECTED_FIELD_LABELS[key] || key
    const sourceLabel =
      source === 'explicit_statement'
        ? '你明确说过'
        : source === 'profile_form'
          ? '资料填写'
          : source
    return `${label}（来源：${sourceLabel}）`
  })
}

/**
 * 更新用户照片（包含人脸比对检查）
 *
 * SECURITY: 只能更新当前用户的照片（auth_session绑定）
 *
 * Flow:
 * 1. User uploads new photos
 * 2. System checks if user has verified_face_anchor (from live video verification)
 * 3. If anchor exists, check face similarity: new photo face vs video face
 * 4. If similarity >= threshold (0.363), save photos
 * 5. If verification_status was "rejected", auto-approve verification
 */
export async function updateProfilePhotosWithFaceCheck(params: {
  photos: string[]
  verification_status?: string
}): Promise<{
  success: boolean
  error?: string
  similarity_score: number
  verification_auto_approved: boolean
  message: string
  photos_count?: number
}> {
  const response = await gatewayJson<{
    success: boolean
    error?: string
    similarity_score: number
    verification_auto_approved: boolean
    message: string
    photos_count?: number
  }>(
    '/v1/profile/photos/update-with-face-check',
    {
      includeAuth: true,
      method: 'POST',
      body: JSON.stringify(params),
    },
  )
  console.log('[updateProfilePhotosWithFaceCheck] 后端返回数据:', {
    success: response.success,
    similarity_score: response.similarity_score,
    verification_auto_approved: response.verification_auto_approved,
    message: response.message,
  })
  return response
}
