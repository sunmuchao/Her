'use client'

import { Suspense, lazy } from 'react'
import type {
  AssessmentCard,
  AssessmentFeedbackCard as AssessmentFeedbackCardType,
  AssessmentIntroCard as AssessmentIntroCardType,
  AssessmentQuestionCard as AssessmentQuestionCardType,
  AssessmentResultCard as AssessmentResultCardType,
  AssessmentInterpretationCard as AssessmentInterpretationCardType,
} from '@/lib/api/endpoints/assessment'

import { AssessmentFeedbackCard } from './AssessmentFeedbackCard'
import { AssessmentIntroCard } from './AssessmentIntroCard'
import { AssessmentQuestionCard } from './AssessmentQuestionCard'
import { AssessmentResultSkeleton } from './AssessmentSkeleton'

// Lazy load the result card as it's heavy with the radar chart
const AssessmentResultCard = lazy(() => 
  import('./AssessmentResultCard').then(mod => ({ default: mod.AssessmentResultCard }))
)

// Type guards for better type safety
function isIntroCard(card: AssessmentCard): card is AssessmentIntroCardType {
  return card.card_type === 'assessment_intro'
}

function isQuestionCard(card: AssessmentCard): card is AssessmentQuestionCardType {
  return card.card_type === 'assessment_question'
}

function isFeedbackCard(card: AssessmentCard): card is AssessmentFeedbackCardType {
  return card.card_type === 'assessment_feedback'
}

function isResultCard(card: AssessmentCard): card is AssessmentResultCardType {
  return card.card_type === 'assessment_result'
}

function isInterpretationCard(card: AssessmentCard): card is AssessmentInterpretationCardType {
  return card.card_type === 'assessment_interpretation'
}

export interface AssessmentCardRendererProps {
  card: AssessmentCard
  onStart: () => void
  onAnswer: (answer: string) => void
  onContinue: () => void
  onContinueChat: () => void
  onPrevious?: () => void
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
  onShare?: () => void
  isResumed?: boolean
  answeredCount?: number
  isSubmitting?: boolean
}

export function AssessmentCardRenderer({
  card,
  onStart,
  onAnswer,
  onContinue,
  onContinueChat,
  onPrevious,
  onAddLabels,
  onShare,
  isResumed = false,
  answeredCount = 0,
  isSubmitting = false,
}: AssessmentCardRendererProps) {
  if (isIntroCard(card)) {
    return (
      <AssessmentIntroCard
        data={card.intro_data}
        onStart={onStart}
        isResumed={isResumed || card.resumed}
        answeredCount={answeredCount || card.answered_count || 0}
      />
    )
  }

  if (isQuestionCard(card)) {
    return (
      <AssessmentQuestionCard
        data={card.question_data}
        onAnswer={onAnswer}
        onPrevious={onPrevious}
        isSubmitting={isSubmitting}
      />
    )
  }

  if (isFeedbackCard(card)) {
    return (
      <AssessmentFeedbackCard
        data={card.feedback_data}
        onContinue={onContinue}
      />
    )
  }

  if (isResultCard(card)) {
    return (
      <Suspense fallback={<AssessmentResultSkeleton />}>
        <AssessmentResultCard
          data={card.result_data}
          onAddLabels={onAddLabels}
          onShare={onShare}
        />
      </Suspense>
    )
  }

  if (isInterpretationCard(card)) {
    return (
      <div className="rounded-3xl border border-border bg-card p-5 shadow-sm animate-scale-in">
        <div className="text-xs uppercase tracking-widest text-muted-foreground">
          {"AI 解读"}
        </div>
        <p className="mt-3 text-sm leading-relaxed">
          {card.interpretation_data.summary}
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          {card.interpretation_data.love_style}
        </p>
        <div className="mt-4 space-y-2">
          {card.interpretation_data.match_suggestions.map((item) => (
            <div key={item} className="rounded-2xl bg-secondary/40 px-3 py-2 text-sm">
              {item}
            </div>
          ))}
        </div>
        <button
          className="mt-4 w-full rounded-xl bg-primary px-4 py-3 text-sm text-primary-foreground font-medium transition-colors hover:bg-primary/90"
          onClick={onContinueChat}
        >
          {"回到聊天"}
        </button>
      </div>
    )
  }

  // Fallback for unknown card types
  return null
}
