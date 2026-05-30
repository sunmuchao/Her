import type { VerificationItemView } from '@/lib/trust/map-trust-hub'

/**
 * Profile 页面统一视图类型
 *
 * 用于 ProfilePage 组件渲染，聚合多个数据源的数据
 */
export type ProfileView = {
  /** 用户名 */
  name: string
  /** 年龄 */
  age?: number
  /** 城市 */
  city: string
  /** 头像 URL */
  avatar: string
  /** 个人简介 */
  headline: string
  /** 是否已认证 */
  verified: boolean
  /** 职业 */
  occupation: string
  /** 学历 */
  education: string
  /** 关系目标 */
  relationshipGoal: string
  /** 用户标签（从已收集偏好提取） */
  tags: string[]
  /** 认证项目列表 */
  verificationItems: VerificationItemView[]
}

/**
 * 默认 Profile 视图（用于 fallback）
 */
export const DEFAULT_PROFILE_VIEW: ProfileView = {
  name: '用户',
  age: undefined,
  city: '待完善',
  avatar: '/placeholder-avatar.png',
  headline: '登录后完善你的资料',
  verified: false,
  occupation: '待完善',
  education: '',
  relationshipGoal: '',
  tags: ['待完善'],
  verificationItems: [],
}