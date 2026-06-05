import type { ProxyIntroCase } from '@/lib/api/endpoints/proxy-intro'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'
import { mapTrustHubPendingActions, type TrustHubVerificationItem } from '@/lib/trust/map-trust-hub'

/**
 * 活跃关系视图数据
 */
export interface ActiveRelationship {
  /** 会话 ID */
  id: string
  /** 牵线 case ID */
  caseId: string
  /** 对方姓名 */
  name: string
  /** 关系阶段 */
  stage: string
  /** 最新消息 */
  lastMessage: string
  /** 最新消息时间 */
  lastMessageTime: string
  /** 是否已认证 */
  verified: boolean
  /** 对方头像 */
  image: string
  /** 未读消息数 */
  unreadCount: number
  /** 对方 profile ID */
  counterpartId?: string
  /** 小雅是否有未读私信 */
  hasXiaoyaUnread?: boolean
  /** 小雅会话 ID */
  xiaoyaConversationId?: string
  /** 小雅最新私信内容 */
  xiaoyaLastMessage?: string
}

/**
 * 牵线中项视图数据
 */
export interface PendingIntroItem extends ProxyIntroCase {
  /** 等待天数（用于显示） */
  waitingDays?: number | null
}

/**
 * 小雅未读数据
 */
export interface XiaoyaUnreadData {
  hasUnread: boolean
  conversationId: string
  lastMessage: string
}

/**
 * 排序优先级：置顶 > 未读 > 最新消息时间
 */
function sortByPriority(a: ActiveRelationship, b: ActiveRelationship, pinnedIds: Record<string, boolean>): number {
  const pinDiff = Number(Boolean(pinnedIds[b.caseId])) - Number(Boolean(pinnedIds[a.caseId]))
  if (pinDiff !== 0) return pinDiff
  const unreadDiff = Number(b.unreadCount > 0) - Number(a.unreadCount > 0)
  if (unreadDiff !== 0) return unreadDiff
  return String(b.lastMessageTime).localeCompare(String(a.lastMessageTime))
}

/**
 * 构建活跃关系视图数据
 *
 * 从 ProxyIntroCase 数组中提取活跃对话，
 * 转换为 ActiveRelationship 类型，用于 RelationshipsPage 渲染
 *
 * @param cases 牵线 cases 数组
 * @param lastMessagesByCaseId 各 case 的最新消息
 * @param unreadByCaseId 各 case 的未读数
 * @param xiaoyaUnreadByCaseId 各 case 的小雅未读数据
 * @param pinnedIds 置顶状态
 * @returns 排序后的活跃关系数组
 */
export function buildActiveRelationships(
  cases: ProxyIntroCase[],
  lastMessagesByCaseId: Record<string, { content: string; time: string }>,
  unreadByCaseId: Record<string, number>,
  xiaoyaUnreadByCaseId: Record<string, XiaoyaUnreadData>,
  pinnedIds: Record<string, boolean> = {},
): ActiveRelationship[] {
  return cases
    .filter((item) => item.main_conversation_id)
    .map((item) => {
      const caseIdStr = String(item.case_id)
      const lastMsgData = lastMessagesByCaseId[caseIdStr]
      const xiaoyaData = xiaoyaUnreadByCaseId[caseIdStr]

      return {
        id: String(item.main_conversation_id),
        caseId: caseIdStr,
        name: item.counterpart_name || '对方',
        stage: item.stage_label || '已开聊',
        lastMessage: lastMsgData?.content || '开始聊天吧',
        lastMessageTime: lastMsgData?.time || item.updated_at || item.created_at || '刚刚',
        verified: true,
        image: resolveProfileImageUrl(item.counterpart_image ?? undefined, PLACEHOLDER_AVATAR),
        unreadCount: unreadByCaseId[caseIdStr] || 0,
        counterpartId: item.counterpart_profile_id ? String(item.counterpart_profile_id) : undefined,
        // 小雅私信相关字段
        hasXiaoyaUnread: xiaoyaData?.hasUnread || false,
        xiaoyaConversationId: xiaoyaData?.conversationId,
        xiaoyaLastMessage: xiaoyaData?.lastMessage,
      }
    })
    .sort((a, b) => sortByPriority(a, b, pinnedIds))
}

/**
 * 构建牵线中项视图数据
 *
 * 从 ProxyIntroCase 数组中提取牵线中的项，
 * 排除掉作为被请求方且等待回复的 case（这些显示在推荐来信中）
 *
 * @param cases 牵线 cases 数组
 * @returns 牵线中项数组
 */
export function buildPendingIntroItems(cases: ProxyIntroCase[]): PendingIntroItem[] {
  return cases
    .filter((item) => {
      // 排除掉作为被请求方且等待回复的 case
      if (item.role === 'candidate' && item.case_status === 'awaiting_reply') {
        return false
      }
      return !item.main_conversation_id
    })
    .map((item) => ({
      ...item,
      waitingDays: getWaitingDays(item),
    }))
}

/**
 * 计算等待天数
 *
 * @param item 牵线 case
 * @returns 等待天数（awaiting_reply 状态才有）
 */
export function getWaitingDays(item: ProxyIntroCase): number | null {
  if (item.case_status !== 'awaiting_reply') return null
  const updatedAt = item.updated_at || item.created_at
  if (!updatedAt) return null
  try {
    const date = new Date(updatedAt)
    const now = new Date()
    return Math.floor((now.getTime() - date.getTime()) / 86400000)
  } catch {
    return null
  }
}

/**
 * 构建待处理认证项视图数据
 *
 * 从 TrustHub 数据中提取待处理的认证项
 *
 * @param trustHub TrustHub 数据
 * @returns 待处理认证项数组
 */
export function buildPendingVerificationActions(trustHub: unknown) {
  const data = trustHub as { trust_hub?: { verification_center?: { items?: TrustHubVerificationItem[] } } } | null
  return mapTrustHubPendingActions(data?.trust_hub?.verification_center?.items).map((item) => ({
    id: item.id,
    type: 'verification' as const,
    title: item.title,
    description: item.description,
  }))
}

/**
 * 构建阶段提示文案
 *
 * 根据牵线 case 的状态生成提示文案
 *
 * @param item 牵线 case
 * @returns 阶段提示文案
 */
export function buildStageTip(item: ProxyIntroCase): string {
  const name = item.counterpart_name || '对方'
  const stage = item.stage_label || '牵线中'
  if (item.main_conversation_id) return `你和${name}已经进入聊天`
  if (item.case_status === 'awaiting_reply') {
    if (item.role === 'requester') {
      return '已把您推荐给对方，等他回复'
    }
    return `已把${name}推荐给对方，等她回复`
  }
  if (item.case_status === 'accepted') return `${name}也愿意认识，可以开始聊天了`
  if (item.case_status === 'declined') return `${name}这次先不考虑`
  if (item.case_status === 'timed_out') return `${name}暂时没有回复`
  return `${name}当前状态：${stage}`
}

/**
 * 格式化相对时间
 *
 * @param timeStr 时间字符串
 * @returns 相对时间文案（如"刚刚"、"5分钟前"）
 */
export function formatRelativeTime(timeStr: string): string {
  if (!timeStr) return '刚刚'
  try {
    const date = new Date(timeStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return `${diffMins}分钟前`
    if (diffHours < 24) return `${diffHours}小时前`
    if (diffDays < 7) return `${diffDays}天前`
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  } catch {
    return timeStr
  }
}
