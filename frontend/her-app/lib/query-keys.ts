// Query Keys 定义 - 用于缓存标识
export const queryKeys = {
  // 用户相关
  authMe: ['auth', 'me'] as const,
  profileFacts: ['profile', 'facts'] as const,

  // 信任中心
  trustHub: (userId: string, profileId?: number) => ['trust', 'hub', userId, profileId] as const,

  // 已收集偏好
  collectedStatements: ['collected', 'statements'] as const,

  // 认证状态
  verificationSubmissions: ['verification', 'submissions'] as const,
  verificationNotifications: ['verification', 'notifications'] as const,
  fieldVerifications: ['verification', 'fields'] as const,

  // 关系页面
  proxyIntroCases: ['proxy-intro', 'cases'] as const,
  relationshipsUnread: ['relationships', 'unread'] as const,

  // 聊天
  caseConversationTimeline: (caseId: string, userId: string) => ['chat', 'timeline', caseId, userId] as const,
}