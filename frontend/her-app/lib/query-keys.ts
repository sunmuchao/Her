// Query Keys 定义 - 用于缓存标识
export const queryKeys = {
  // 用户相关
  authMe: ['auth', 'me'] as const,
  profileFacts: ['profile', 'facts'] as const,

  // 信任中心
  trustHub: (userId: string, profileId?: number) => ['trust', 'hub', userId, profileId] as const,

  // 已收集偏好
  collectedStatements: (profileId?: number) => ['collected', 'statements', profileId ?? 'anonymous'] as const,

  // 认证状态
  verificationSubmissions: ['verification', 'submissions'] as const,
  verificationNotifications: ['verification', 'notifications'] as const,
  fieldVerifications: ['verification', 'fields'] as const,

  // 关系页面
  proxyIntroCases: ['proxy-intro', 'cases'] as const,
  relationshipsUnread: ['relationships', 'unread'] as const,

  // 聊天
  caseConversationTimeline: (caseId: string, userId: string) => ['chat', 'timeline', caseId, userId] as const,

  // 运营工作台
  opsWorkbenchSummary: ['ops', 'workbench', 'summary'] as const,

  // 审核队列
  reviewQueue: (params: { status?: string; field_key?: string; limit?: number }) =>
    ['review', 'queue', params] as const,
  videoReviewQueue: ['review', 'video', 'queue'] as const,
  reportReviewQueue: ['review', 'report', 'queue'] as const,
  photoReviewQueue: ['review', 'photo', 'queue'] as const,
  appealReviewQueue: ['review', 'appeal', 'queue'] as const,

  // 用户信息
  userInfo: (profileId: number, sourceDsn?: string, sourceTableName?: string) =>
    ['user', 'info', profileId, sourceDsn ?? 'default', sourceTableName ?? 'default'] as const,
}
