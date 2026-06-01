'use client'

import { useState, useCallback, useMemo, useEffect } from 'react'
import {
  type AssessmentCard,
  type AssessmentIntroCard,
  type AssessmentQuestionCard,
  type AssessmentFeedbackCard,
  type AssessmentResultCard,
  type AssessmentInterpretationCard,
  getOrCreateAssessment,
  beginAssessment,
  answerAssessment,
  addAssessmentLabels,
} from '@/lib/api/endpoints/assessment'

// ============ Type Guards ============

export function isIntroCard(card: AssessmentCard): card is AssessmentIntroCard {
  return card.card_type === 'assessment_intro'
}

export function isQuestionCard(card: AssessmentCard): card is AssessmentQuestionCard {
  return card.card_type === 'assessment_question'
}

export function isFeedbackCard(card: AssessmentCard): card is AssessmentFeedbackCard {
  return card.card_type === 'assessment_feedback'
}

export function isResultCard(card: AssessmentCard): card is AssessmentResultCard {
  return card.card_type === 'assessment_result'
}

export function isInterpretationCard(card: AssessmentCard): card is AssessmentInterpretationCard {
  return card.card_type === 'assessment_interpretation'
}

// ============ MBTI Dimension Helpers ============

export interface MBTIDimension {
  key: string
  label: string
  name: string
  leftTrait: string
  rightTrait: string
  leftCode: string
  rightCode: string
  color: string
  icon: string
}

export const MBTI_DIMENSIONS: MBTIDimension[] = [
  {
    key: 'EI',
    label: 'E/I',
    name: '社交能量',
    leftTrait: '外向',
    rightTrait: '内向',
    leftCode: 'E',
    rightCode: 'I',
    color: 'rose',
    icon: 'users',
  },
  {
    key: 'SN',
    label: 'S/N',
    name: '信息获取',
    leftTrait: '实感',
    rightTrait: '直觉',
    leftCode: 'S',
    rightCode: 'N',
    color: 'gold',
    icon: 'eye',
  },
  {
    key: 'TF',
    label: 'T/F',
    name: '决策方式',
    leftTrait: '思考',
    rightTrait: '情感',
    leftCode: 'T',
    rightCode: 'F',
    color: 'taupe',
    icon: 'heart',
  },
  {
    key: 'JP',
    label: 'J/P',
    name: '生活态度',
    leftTrait: '判断',
    rightTrait: '知觉',
    leftCode: 'J',
    rightCode: 'P',
    color: 'primary',
    icon: 'compass',
  },
]

// Question to Dimension mapping (5 questions per dimension)
export function getQuestionDimension(questionNumber: number): MBTIDimension {
  const dimensionIndex = Math.floor((questionNumber - 1) / 5)
  return MBTI_DIMENSIONS[Math.min(dimensionIndex, 3)]
}

export function getDimensionProgress(questionNumber: number, totalQuestions: number): {
  currentDimension: MBTIDimension
  dimensionIndex: number
  questionInDimension: number
  questionsPerDimension: number
} {
  const questionsPerDimension = Math.ceil(totalQuestions / 4)
  const dimensionIndex = Math.floor((questionNumber - 1) / questionsPerDimension)
  const questionInDimension = ((questionNumber - 1) % questionsPerDimension) + 1
  
  return {
    currentDimension: MBTI_DIMENSIONS[Math.min(dimensionIndex, 3)],
    dimensionIndex: Math.min(dimensionIndex, 3),
    questionInDimension,
    questionsPerDimension,
  }
}

// ============ Assessment State ============

export type AssessmentStatus = 'idle' | 'loading' | 'active' | 'error'

export interface AssessmentError {
  message: string
  code?: string
  retryable: boolean
}

export interface UseAssessmentReturn {
  // State
  card: AssessmentCard | null
  assessmentId: string | null
  status: AssessmentStatus
  error: AssessmentError | null
  questionHistory: AssessmentQuestionCard['question_data'][]
  isResumed: boolean
  answeredCount: number
  
  // Actions
  openAssessment: () => Promise<void>
  handleStart: () => Promise<void>
  handleAnswer: (answer: string) => Promise<void>
  handleContinue: () => void
  handlePrevious: () => void
  handleAddLabels: (labels: string[]) => Promise<void>
  clearAssessment: () => void
  retry: () => Promise<void>
  
  // Computed
  canGoPrevious: boolean
  currentDimension: MBTIDimension | null
  dimensionProgress: ReturnType<typeof getDimensionProgress> | null
}

export function useAssessment(userKey: string): UseAssessmentReturn {
  const [card, setCard] = useState<AssessmentCard | null>(null)
  const [assessmentId, setAssessmentId] = useState<string | null>(null)
  const [questionHistory, setQuestionHistory] = useState<AssessmentQuestionCard['question_data'][]>([])
  const [status, setStatus] = useState<AssessmentStatus>('idle')
  const [error, setError] = useState<AssessmentError | null>(null)
  const [isResumed, setIsResumed] = useState(false)
  const [answeredCount, setAnsweredCount] = useState(0)

  const clearAssessment = useCallback(() => {
    setCard(null)
    setAssessmentId(null)
    setQuestionHistory([])
    setStatus('idle')
    setError(null)
    setIsResumed(false)
    setAnsweredCount(0)
  }, [])

  const openAssessment = useCallback(async () => {
    setStatus('loading')
    setError(null)
    
    try {
      const intro = await getOrCreateAssessment(userKey)
      setAssessmentId(intro.assessment_id)
      setCard(intro)
      setQuestionHistory([])
      setStatus('active')
      
      if (intro.resumed) {
        setIsResumed(true)
        setAnsweredCount(intro.answered_count ?? 0)
      }
    } catch (err) {
      setStatus('error')
      setError({
        message: err instanceof Error ? err.message : '加载测评失败，请稍后重试',
        retryable: true,
      })
    }
  }, [userKey])

  const handleStart = useCallback(async () => {
    if (!assessmentId) return
    
    setStatus('loading')
    try {
      const next = await beginAssessment(assessmentId)
      setCard(next)
      setStatus('active')
    } catch (err) {
      setStatus('error')
      setError({
        message: err instanceof Error ? err.message : '开始测评失败，请稍后重试',
        retryable: true,
      })
    }
  }, [assessmentId])

  const handleAnswer = useCallback(async (answer: string) => {
    if (!assessmentId || !card || !isQuestionCard(card)) return
    
    // Save current question to history for back navigation
    setQuestionHistory(prev => [...prev, card.question_data])
    
    setStatus('loading')
    try {
      const next = await answerAssessment({
        assessmentId,
        questionIndex: card.question_data.current_question - 1,
        answer,
        userKey,
      })
      setCard(next)
      setStatus('active')
    } catch (err) {
      // Restore history on error
      setQuestionHistory(prev => prev.slice(0, -1))
      setStatus('error')
      setError({
        message: err instanceof Error ? err.message : '提交答案失败，请稍后重试',
        retryable: true,
      })
    }
  }, [assessmentId, card, userKey])

  const handleContinue = useCallback(() => {
    if (!card || !isFeedbackCard(card) || !assessmentId) return
    
    setCard({
      card_type: 'assessment_question',
      assessment_id: assessmentId,
      question_data: card.next_question,
    })
  }, [card, assessmentId])

  const handlePrevious = useCallback(() => {
    if (questionHistory.length === 0 || !assessmentId) return
    
    const previous = questionHistory[questionHistory.length - 1]
    setQuestionHistory(prev => prev.slice(0, -1))
    setCard({
      card_type: 'assessment_question',
      assessment_id: assessmentId,
      question_data: previous,
    })
  }, [questionHistory, assessmentId])

  const handleAddLabels = useCallback(async (labels: string[]) => {
    await addAssessmentLabels(userKey, labels)
  }, [userKey])

  const retry = useCallback(async () => {
    if (status === 'error') {
      await openAssessment()
    }
  }, [status, openAssessment])

  // Computed values
  const canGoPrevious = questionHistory.length > 0

  const currentDimension = useMemo(() => {
    if (!card || !isQuestionCard(card)) return null
    return getQuestionDimension(card.question_data.current_question)
  }, [card])

  const dimensionProgress = useMemo(() => {
    if (!card || !isQuestionCard(card)) return null
    return getDimensionProgress(
      card.question_data.current_question,
      card.question_data.total_questions
    )
  }, [card])

  return {
    card,
    assessmentId,
    status,
    error,
    questionHistory,
    isResumed,
    answeredCount,
    openAssessment,
    handleStart,
    handleAnswer,
    handleContinue,
    handlePrevious,
    handleAddLabels,
    clearAssessment,
    retry,
    canGoPrevious,
    currentDimension,
    dimensionProgress,
  }
}
