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
      has_values_test: boolean
      has_attachment_test: boolean
      has_personality_type: boolean
      has_big_five: boolean
      overall_completeness: number
    }
    attachment_test_result?: {
      primary_style: string  // "secure" | "anxious" | "avoidant" | "fearful"
      anxiety_score: number
      avoidance_score: number
    }
    personality_type_result?: {
      mbti_type: string  // "INFP" 等
    }
    values_test_result?: {
      values_dimensions?: {
        stability_vs_growth?: string
      }
    }
  }
}
