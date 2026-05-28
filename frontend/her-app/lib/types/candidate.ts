export type CandidatePreview = {
  id: string
  name: string
  age?: number
  city?: string
  occupation?: string
  education?: string
  verified?: boolean
  matchScore?: number
  image?: string
  matchReason?: string
  message?: string
  recommendationId?: number
  subscriptionId?: string
  // 新增：被动推荐场景需要的字段
  caseId?: string // 案件 ID（被动推荐场景）
  viewType?: 'delayed' | 'matched' | 'interest' | 'candidate' // 卡片类型
}
