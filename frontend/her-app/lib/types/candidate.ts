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

  // ===== Phase 1: 测评画像字段 =====
  personality_reasons?: string[]  // 测评推荐理由（如["依恋风格互补：你的安全型能稳住TA的焦虑倾向"])
  personality_match_context?: {
    availability?: {
      has_values?: boolean
      has_attachment?: boolean
      has_mbti?: boolean
      has_big_five?: boolean
      has_sternberg?: boolean
      overall_completeness: number
    }
    attachment?: {
      type_code?: string
      anxiety?: number
      avoidance?: number
    }
    mbti?: {
      type_code?: string
      scores?: Record<string, number>
    }
    big_five?: {
      scores?: Record<string, number>
    }
    values?: {
      value_type?: string
      top_values?: string[]
      tensions?: string[]
    }
    sternberg?: {
      type_code?: string
      scores?: Record<string, number>
    }
  }
}
