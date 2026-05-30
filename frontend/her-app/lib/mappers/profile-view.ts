import type { AuthMeData } from '@/lib/hooks/use-auth-me'
import type { ProfileFactsData } from '@/lib/hooks/use-profile-facts'
import type { CollectedStatementsData } from '@/lib/hooks/use-collected'
import type { TrustHubData } from '@/lib/hooks/use-trust-hub'
import type { ProfileView } from '@/lib/types/profile-view'
import { DEFAULT_PROFILE_VIEW } from '@/lib/types/profile-view'
import {
  mapTrustHubVerificationItems,
  type VerificationItemView,
} from '@/lib/trust/map-trust-hub'
import { extractPreferredTraits } from '@/lib/api/endpoints/persona'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'

/**
 * 安全获取字符串值
 * 从多个可能的值中取第一个有效的字符串
 * 支持 unknown 类型，自动过滤非字符串/数字值
 */
function safeString(...values: unknown[]): string {
  for (const v of values) {
    if (v !== null && v !== undefined && v !== '') {
      if (typeof v === 'string' || typeof v === 'number') {
        return String(v)
      }
    }
  }
  return ''
}

/**
 * 安全获取数值
 */
function safeNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && !isNaN(value)) {
    return value
  }
  return undefined
}

/**
 * 安全获取布尔值
 */
function safeBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === 'true' || value === '1') return true
  return false
}

/**
 * 构建 Profile 视图数据
 *
 * 从多个数据源（Auth、Facts、Collected、TrustHub）聚合数据，
 * 转换为 ProfileView 类型，用于 ProfilePage 渲染
 */
export function buildProfileView(
  auth: AuthMeData | undefined,
  facts: ProfileFactsData | undefined,
  collected: CollectedStatementsData | undefined,
  trust: TrustHubData | undefined,
): ProfileView {
  if (!auth && !facts) {
    return DEFAULT_PROFILE_VIEW
  }

  const user = auth?.user ?? {}
  const rawProfile = facts?.profile_facts ?? {}
  const collectedStatements = collected?.collected_statements ?? {}
  const collectedItems = collected?.collected_items ?? {}

  // 提取标签（从 preferred_traits 字段，用户手动编辑）
  let tags: string[] = []
  if (Object.keys(collectedStatements).length > 0) {
    tags = extractPreferredTraits(collectedStatements).slice(0, 6)
  }

  // 提取认证项目
  let verificationItems: VerificationItemView[] = []
  if (trust?.trust_hub?.verification_center?.items) {
    verificationItems = mapTrustHubVerificationItems(
      trust.trust_hub.verification_center.items,
    )
  }

  return {
    name: safeString(user.display_name, rawProfile.name, '用户'),
    age: safeNumber(rawProfile.age),
    city: safeString(rawProfile.city, rawProfile.settlement_city, '待完善'),
    avatar: safeString(user.avatar_url, rawProfile.avatar_url, PLACEHOLDER_AVATAR),
    headline: safeString(
      rawProfile.headline,
      rawProfile.bio,
      rawProfile.public_notes,
      '认真关系，从认真了解开始',
    ),
    verified: safeBoolean(rawProfile.verified) || safeBoolean(rawProfile.live_video_verified),
    occupation: safeString(
      rawProfile.public_job,
      rawProfile.job,
      rawProfile.occupation,
      '待完善',
    ),
    education: safeString(rawProfile.public_education, rawProfile.education, ''),
    relationshipGoal: safeString(rawProfile.relationship_goal, ''),
    tags: tags.length > 0 ? tags : DEFAULT_PROFILE_VIEW.tags,
    verificationItems,
  }
}

/**
 * 计算认证进度
 */
export function calculateVerificationProgress(items: VerificationItemView[]): {
  verifiedCount: number
  total: number
  progress: number
} {
  const verifiedCount = items.filter((item) => item.status === 'verified').length
  const total = items.length
  const progress = total > 0 ? (verifiedCount / total) * 100 : 0
  return { verifiedCount, total, progress }
}