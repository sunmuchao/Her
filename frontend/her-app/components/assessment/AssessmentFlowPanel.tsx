'use client'

import { useEffect, useMemo, useState } from 'react'
import { X, AlertCircle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  answerAssessment,
  beginAssessment,
  type AssessmentCard,
  type AssessmentQuestionCard,
  getOrCreateAssessment,
  addAssessmentLabels,
} from '@/lib/api/endpoints/assessment'

import { AssessmentCardRenderer } from './AssessmentCardRenderer'
import { AssessmentSkeleton, AssessmentIntroSkeleton } from './AssessmentSkeleton'
import { getAssessmentTheme, type AssessmentType } from './assessment-themes'

export function AssessmentFlowPanel({
  open,
  userKey,
  onClose,
}: {
  open: boolean
  userKey: string
  onClose: () => void
}) {
  const [card, setCard] = useState<AssessmentCard | null>(null)
  const [assessmentId, setAssessmentId] = useState<string | null>(null)
  const [questionHistory, setQuestionHistory] = useState<AssessmentQuestionCard['question_data'][]>([])
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isResumed, setIsResumed] = useState(false)
  const [answeredCount, setAnsweredCount] = useState(0)

  const currentAssessmentType: AssessmentType | undefined =
    card?.assessment_type || (card?.card_type === 'assessment_result' ? card.assessment_type : undefined)
  const currentTheme = getAssessmentTheme(currentAssessmentType)

  const initializeAssessment = async () => {
    setError(null)
    try {
      const intro = await getOrCreateAssessment(userKey)
      setAssessmentId(intro.assessment_id)
      setCard(intro)
      setQuestionHistory([])
      
      if (intro.resumed) {
        setIsResumed(true)
        setAnsweredCount(intro.answered_count || 0)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败，请重试')
    }
  }

  useEffect(() => {
    if (!open) return
    let cancelled = false

    void getOrCreateAssessment(userKey).then((intro) => {
      if (cancelled) return
      setAssessmentId(intro.assessment_id)
      setCard(intro)
      setQuestionHistory([])
      
      if (intro.resumed) {
        setIsResumed(true)
        setAnsweredCount(intro.answered_count || 0)
      }
    }).catch((err) => {
      if (cancelled) return
      setError(err instanceof Error ? err.message : '加载失败，请重试')
    })

    return () => {
      cancelled = true
    }
  }, [open, userKey])

  const loading = useMemo(() => open && !card && !error, [open, card, error])

  if (!open) return null

  const close = () => {
    setCard(null)
    setAssessmentId(null)
    setError(null)
    setIsResumed(false)
    setAnsweredCount(0)
    onClose()
  }

  const handleAddLabels = async (selectedLabels: string[]) => {
    await addAssessmentLabels(userKey, selectedLabels)
  }

  const handleStart = async () => {
    if (!assessmentId) return
    setIsSubmitting(true)
    setError(null)
    try {
      const next = await beginAssessment(assessmentId)
      setCard(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : '开始测评失败，请重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAnswer = async (answer: string) => {
    if (!assessmentId || card?.card_type !== 'assessment_question') return
    setIsSubmitting(true)
    setError(null)
    
    const currentQuestion = card.question_data
    setQuestionHistory((prev) => [...prev, currentQuestion])
    
    try {
      const next = await answerAssessment({
        assessmentId,
        questionIndex: currentQuestion.current_question - 1,
        answer,
        userKey,
      })
      setCard(next)
    } catch (err) {
      // Rollback on error
      setQuestionHistory((prev) => prev.slice(0, -1))
      setError(err instanceof Error ? err.message : '提交答案失败，请重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleContinue = () => {
    if (card?.card_type !== 'assessment_feedback' || !assessmentId) return
    setCard({
      card_type: 'assessment_question',
      assessment_id: assessmentId,
      question_data: card.next_question,
    })
  }

  const handlePrevious = questionHistory.length > 0
    ? () => {
        const previous = questionHistory[questionHistory.length - 1]
        setQuestionHistory((prev) => prev.slice(0, -1))
        setCard({
          card_type: 'assessment_question',
          assessment_id: assessmentId!,
          question_data: previous,
        })
      }
    : undefined

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-3 animate-fade-in">
      <div 
        className="w-full max-w-lg rounded-[28px] bg-background p-3 shadow-2xl animate-slide-up"
        role="dialog"
        aria-modal="true"
        aria-labelledby="assessment-title"
      >
        {/* Header */}
        <div className="mb-3 flex items-center justify-between px-2">
          <div>
            <div id="assessment-title" className="text-sm font-medium">
              {currentTheme.name}
            </div>
            <div className="text-xs text-muted-foreground">
              {`${currentTheme.duration} · ${currentTheme.questionCount}题`}
            </div>
          </div>
          <Button 
            variant="ghost" 
            size="icon-sm" 
            onClick={close}
            aria-label="关闭测评"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Error State */}
        {error && (
          <div className="rounded-3xl border border-destructive/30 bg-destructive/5 p-5">
            <div className="flex items-center gap-3 mb-3">
              <AlertCircle className="w-5 h-5 text-destructive" />
              <span className="text-sm font-medium text-destructive">{"出错了"}</span>
            </div>
            <p className="text-sm text-muted-foreground mb-4">{error}</p>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={initializeAssessment}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              {"重试"}
            </Button>
          </div>
        )}

        {/* Loading State */}
        {loading && !error && (
          card?.card_type === 'assessment_question' 
            ? <AssessmentSkeleton />
            : <AssessmentIntroSkeleton />
        )}

        {/* Content */}
        {card && assessmentId && !error && (
          <AssessmentCardRenderer
            card={card}
            onStart={handleStart}
            onAnswer={handleAnswer}
            onContinue={handleContinue}
            onContinueChat={close}
            onPrevious={handlePrevious}
            onAddLabels={handleAddLabels}
            isResumed={isResumed}
            answeredCount={answeredCount}
            isSubmitting={isSubmitting}
          />
        )}
      </div>
    </div>
  )
}
