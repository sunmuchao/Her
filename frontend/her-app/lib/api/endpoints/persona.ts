import { gatewayJson } from '@/lib/api/client'
import { getProfileId } from '@/lib/auth/session'

export type PersonaPatchRequest = {
  patch: {
    preferred_traits?: string[]
    must_have_tags?: string[]
    must_not_have_tags?: string[]
    disliked_traits?: string[]
  }
}

export type PersonaPatchResponse = {
  profile_id: number
  applied_fields: Array<{
    field: string
    applied_to_persona: boolean
    value?: unknown
  }>
  skipped_fields: Array<{
    field: string
    applied_to_persona: boolean
    reason?: string
  }>
}

export type PersonaErrorResponse = {
  error: {
    code: string
    message: string
  }
}

/**
 * 更新用户画像标签
 *
 * @param tags 用户输入的标签列表（存入 preferred_traits 字段）
 * @returns 更新结果
 */
export async function patchPersonaTags(tags: string[]): Promise<PersonaPatchResponse> {
  const body: PersonaPatchRequest = {
    patch: {
      preferred_traits: tags,
    },
  }

  return gatewayJson<PersonaPatchResponse>('/v1/persona/patch', {
    method: 'PATCH',
    includeAuth: true,
    body: JSON.stringify(body),
  })
}

/**
 * 从 collected statements 中提取 preferred_traits 标签
 *
 * @param statements 收集的画像数据
 * @returns 标签列表
 */
export function extractPreferredTraits(statements: Record<string, unknown>): string[] {
  const traits = statements.preferred_traits
  if (!traits) return []

  // 如果是字符串（CSV 格式），分割成数组
  if (typeof traits === 'string') {
    return traits.split(/[,，]/).map((t) => t.trim()).filter(Boolean)
  }

  // 如果已经是数组，直接返回
  if (Array.isArray(traits)) {
    return traits.map(String).filter(Boolean)
  }

  return []
}