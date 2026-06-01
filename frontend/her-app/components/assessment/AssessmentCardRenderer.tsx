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
import type { ValuesAuctionCard } from '@/lib/api/endpoints/valuesAuction'
import { cn } from '@/lib/utils'
import { type AssessmentType } from './assessment-themes'
import { ValuesAuctionCardRenderer } from '@/components/values-auction'

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

// Values Auction card type guard
function isValuesAuctionCard(card: any): card is ValuesAuctionCard {
  const valuesAuctionTypes = [
    'values_auction_intro',
    'values_auction_traits',
    'values_auction_result',
    'values_auction_interpretation',
    'values_auction_waiting',
    'values_match_analysis',
    'values_auction_history',
    'error',
  ]
  return valuesAuctionTypes.includes(card?.card_type)
}

// Extract assessment type from the card
function getAssessmentTypeFromCard(card: AssessmentCard): AssessmentType | undefined {
  if (isIntroCard(card)) {
    return card.assessment_type
  }
  // Support result card having assessment_type (backend may include it)
  if (isResultCard(card)) {
    return card.assessment_type
  }
  return undefined
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
  assessmentType?: AssessmentType
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
  assessmentType,
}: AssessmentCardRendererProps) {
  // Try to get assessment type from card if not provided
  const resolvedAssessmentType = assessmentType || getAssessmentTypeFromCard(card)

  // Values Auction cards use their own renderer
  if (isValuesAuctionCard(card)) {
    return (
      <ValuesAuctionCardRenderer
        card={card}
        onStart={onStart}
        onContinue={onContinueChat}
      />
    )
  }

  if (isIntroCard(card)) {
    return (
      <AssessmentIntroCard
        data={card.intro_data}
        onStart={onStart}
        isResumed={isResumed || card.resumed}
        answeredCount={answeredCount || card.answered_count || 0}
        assessmentType={resolvedAssessmentType}
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
        assessmentType={resolvedAssessmentType}
      />
    )
  }

  if (isFeedbackCard(card)) {
    return (
      <AssessmentFeedbackCard
        data={card.feedback_data}
        onContinue={onContinue}
        assessmentType={resolvedAssessmentType}
      />
    )
  }

  if (isResultCard(card)) {
    // DEBUG: 检查传递给 AssessmentResultCard 的数据
    console.log('[AssessmentCardRenderer] result card:', {
      cardType: card.card_type,
      assessmentId: card.assessment_id,
      hasResultData: !!card.result_data,
      resultDataKeys: card.result_data ? Object.keys(card.result_data) : [],
      dimensionRowsCount: card.result_data?.dimension_rows?.length || 0,
      labelsCount: card.result_data?.labels?.length || 0,
      dimensionRows: card.result_data?.dimension_rows,
      labels: card.result_data?.labels,
    })

    return (
      <Suspense fallback={<AssessmentResultSkeleton />}>
        <AssessmentResultCard
          data={card.result_data}
          onAddLabels={onAddLabels}
          onShare={onShare}
          assessmentType={resolvedAssessmentType}
        />
      </Suspense>
    )
  }

  if (isInterpretationCard(card)) {
    // Get themed button color
    const buttonClass = resolvedAssessmentType === 'attachment_style' 
      ? 'bg-coral hover:bg-coral/90 text-white' 
      : resolvedAssessmentType === 'love_language' 
        ? 'bg-lavender hover:bg-lavender/90 text-white' 
        : 'bg-primary hover:bg-primary/90'
    
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
          className={cn(
            "mt-4 w-full rounded-xl px-4 py-3 text-sm text-white font-medium transition-colors",
            buttonClass
          )}
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
