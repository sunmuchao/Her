import { gatewayJson, queryString } from '@/lib/api/client'

export type AssessmentIntroCard = {
  card_type: 'assessment_intro'
  assessment_type?: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love'
  assessment_id: string
  intro_data: {
    title: string
    description: string
    duration: string
    reward: string
  }
  resumed?: boolean        // 是否为恢复的测评（断点续传）
  answered_count?: number  // 已答题数量（恢复时使用）
}

export type AssessmentQuestionCard = {
  card_type: 'assessment_question'
  assessment_id: string
  question_data: {
    current_question: number
    total_questions: number
    question_text: string
    options: Array<{ label: string; text: string; score: number }>
    progress: number
    assessment_id: string
  }
}

export type AssessmentFeedbackCard = {
  card_type: 'assessment_feedback'
  assessment_id: string
  feedback_data: {
    dimension: string
    dimension_name: string
    score: number
    feedback_text: string
  }
  next_question: AssessmentQuestionCard['question_data']
}

export type AssessmentResultCard = {
  card_type: 'assessment_result'
  assessment_type?: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love'
  assessment_id: string
  result_data: {
    type_code: string
    scores: Record<string, number>
    dimension_rows?: Array<{
      key: string
      name: string
      score: number
      level: 'high' | 'medium' | 'low'
      trait: string
    }>
    quadrant?: {
      x_key: string
      x_name: string
      x_score: number
      y_key: string
      y_name: string
      y_score: number
      type_code: string
      type_name: string
      quadrants: Record<string, {
        type_code: string
        label: string
      }>
    }
    labels?: string[]
    interpretation_data?: {
      summary: string
      love_style?: string
      match_suggestions?: string[]
      relationship_drive?: string
      triggers?: string
      stabilizers?: string
      common_misread?: string
      communication_advice?: string
      card_tip?: string
      fit_people?: string[]
      friction_people?: string[]
      ecr_basis?: string[]
      quadrant_label?: string
      disclaimer?: string
      extreme_tags?: Array<{
        tag: string
        description: string
      }>
    }
    reward: string
    assessment_id: string
  }
}

export type AssessmentInterpretationCard = {
  card_type: 'assessment_interpretation'
  assessment_id: string
  interpretation_data: {
    summary: string
    love_style?: string
    match_suggestions?: string[]
    relationship_drive?: string
    triggers?: string
    stabilizers?: string
    common_misread?: string
    communication_advice?: string
    card_tip?: string
    fit_people?: string[]
    friction_people?: string[]
    ecr_basis?: string[]
    disclaimer?: string
  }
}

export type AssessmentCard =
  | AssessmentIntroCard
  | AssessmentQuestionCard
  | AssessmentFeedbackCard
  | AssessmentResultCard
  | AssessmentInterpretationCard

export async function startAssessment(
  userKey: string,
  assessmentType: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love' = 'mbti_16'
): Promise<AssessmentIntroCard> {
  return gatewayJson<AssessmentIntroCard>('/v1/assessment/start', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: userKey,
      assessment_type: assessmentType,
    }),
  })
}

/**
 * 获取未完成的测评（断点续传），或创建新测评
 *
 * 防呆机制：用户退出App后，下次进来能接着上次的进度继续做，
 * 不会从第1题重新开始。
 *
 * 如果返回的 intro_data.title 是"继续上次的测评"，说明有未完成的测评
 * resumed=true 表示是恢复的测评
 */
export async function getOrCreateAssessment(
  userKey: string,
  assessmentType: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love' = 'mbti_16'
): Promise<AssessmentIntroCard> {
  return gatewayJson<AssessmentIntroCard>('/v1/assessment/get-or-create', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: userKey,
      assessment_type: assessmentType,
    }),
  })
}

export async function beginAssessment(assessmentId: string): Promise<AssessmentQuestionCard> {
  return gatewayJson<AssessmentQuestionCard>('/v1/assessment/begin', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({ assessment_id: assessmentId }),
  })
}

export async function answerAssessment(params: {
  assessmentId: string
  questionIndex: number
  answer: string
  userKey: string
}): Promise<AssessmentCard> {
  return gatewayJson<AssessmentCard>('/v1/assessment/answer', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      assessment_id: params.assessmentId,
      question_index: params.questionIndex,
      answer: params.answer,
      user_key: params.userKey,
    }),
  })
}

export async function fetchAssessmentInterpretation(params: {
  assessmentId: string
  userKey: string
}): Promise<AssessmentInterpretationCard> {
  return gatewayJson<AssessmentInterpretationCard>('/v1/assessment/interpretation', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      assessment_id: params.assessmentId,
      user_key: params.userKey,
    }),
  })
}

export async function fetchPersonalityTraits(userKey: string) {
  return gatewayJson<{ user_key: string; mbti: unknown; attachment: unknown; big_five: unknown; sternberg: unknown }>(
    `/v1/persona/personality-traits${queryString({ user_key: userKey })}`,
    { includeAuth: true },
  )
}

/**
 * 添加测评标签到个人标签（用户选择后添加）
 *
 * 用户勾选想要的标签后，调用此API将标签添加到 preferred_traits
 */
export async function addAssessmentLabels(userKey: string, labels: string[]): Promise<{
  user_key: string
  added_labels: string[]
  message: string
}> {
  return gatewayJson<{
    user_key: string
    added_labels: string[]
    message: string
  }>('/v1/assessment/add-labels', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: userKey,
      labels,
    }),
  })
}

/**
 * 获取小雅解读消息（用于在对话页面显示）
 *
 * 测评完成后，小雅会主动发送解读消息。
 * 前端在打开小雅对话时调用此API检查是否有新消息。
 */
export async function getXiaoyaMessage(
  userKey: string,
  assessmentType?: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love'
): Promise<{
  has_message: boolean
  message?: string
  assessment_id?: string
}> {
  return gatewayJson<{
    has_message: boolean
    message?: string
    assessment_id?: string
  }>('/v1/assessment/xiaoya-message', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({ user_key: userKey, assessment_type: assessmentType }),
  })
}

/**
 * 标记小雅消息为已读
 *
 * 用户看完小雅解读消息后，调用此API标记为已读
 */
export async function markXiaoyaMessageRead(userKey: string, assessmentId: string): Promise<{
  success: boolean
}> {
  return gatewayJson<{ success: boolean }>('/v1/assessment/xiaoya-read', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: userKey,
      assessment_id: assessmentId,
    }),
  })
}

/**
 * 将小雅消息添加到discovery session的对话历史
 *
 * 这样小雅消息会固定在对话流中，AI也能看到。
 */
export async function addXiaoyaMessageToDiscovery(params: {
  userKey: string
  sessionId: string
  message: string
  resultData?: unknown
  assessmentType?: string  // 新增：支持传递测评类型
}): Promise<{
  success: boolean
  message: string
  item_id: string
}> {
  return gatewayJson<{
    success: boolean
    message: string
    item_id: string
  }>('/v1/assessment/add-xiaoya-to-discovery', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: params.userKey,
      session_id: params.sessionId,
      message: params.message,
      result_data: params.resultData,
      assessment_type: params.assessmentType,  // 新增：传递测评类型
    }),
  })
}
