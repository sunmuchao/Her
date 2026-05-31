import { gatewayJson, queryString } from '@/lib/api/client'

export type AssessmentIntroCard = {
  card_type: 'assessment_intro'
  assessment_type: 'mbti_16'
  assessment_id: string
  intro_data: {
    title: string
    description: string
    duration: string
    reward: string
  }
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
  assessment_id: string
  result_data: {
    type_code: string
    scores: Record<string, number>
    dimension_rows: Array<{
      key: string
      name: string
      score: number
      level: 'high' | 'medium' | 'low'
      trait: string
    }>
    labels: string[]
    reward: string
    assessment_id: string
  }
}

export type AssessmentInterpretationCard = {
  card_type: 'assessment_interpretation'
  assessment_id: string
  interpretation_data: {
    summary: string
    love_style: string
    match_suggestions: string[]
  }
}

export type AssessmentCard =
  | AssessmentIntroCard
  | AssessmentQuestionCard
  | AssessmentFeedbackCard
  | AssessmentResultCard
  | AssessmentInterpretationCard

export async function startAssessment(userKey: string): Promise<AssessmentIntroCard> {
  return gatewayJson<AssessmentIntroCard>('/v1/assessment/start', {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify({
      user_key: userKey,
      assessment_type: 'mbti_16',
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
  return gatewayJson<{ user_key: string; mbti: unknown; attachment: unknown; love_language: unknown }>(
    `/v1/persona/personality-traits${queryString({ user_key: userKey })}`,
    { includeAuth: true },
  )
}
