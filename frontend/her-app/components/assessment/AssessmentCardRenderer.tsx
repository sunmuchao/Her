'use client'

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
import { AssessmentResultCard } from './AssessmentResultCard'

export function AssessmentCardRenderer({
  card,
  onStart,
  onAnswer,
  onContinue,
  onContinueChat,
  onPrevious,
}: {
  card: AssessmentCard
  onStart: () => void
  onAnswer: (answer: string) => void
  onContinue: () => void
  onContinueChat: () => void
  onPrevious?: () => void
}) {
  switch (card.card_type) {
    case 'assessment_intro':
      return <AssessmentIntroCard data={(card as AssessmentIntroCardType).intro_data} onStart={onStart} />
    case 'assessment_question':
      return <AssessmentQuestionCard data={(card as AssessmentQuestionCardType).question_data} onAnswer={onAnswer} onPrevious={onPrevious} />
    case 'assessment_feedback':
      return <AssessmentFeedbackCard data={(card as AssessmentFeedbackCardType).feedback_data} onContinue={onContinue} />
    case 'assessment_result':
      return <AssessmentResultCard data={(card as AssessmentResultCardType).result_data} />
    case 'assessment_interpretation':
      return (
        <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
          <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">AI 解读</div>
          <p className="mt-3 text-sm leading-relaxed">{(card as AssessmentInterpretationCardType).interpretation_data.summary}</p>
          <p className="mt-3 text-sm text-muted-foreground">{(card as AssessmentInterpretationCardType).interpretation_data.love_style}</p>
          <div className="mt-4 space-y-2">
            {(card as AssessmentInterpretationCardType).interpretation_data.match_suggestions.map((item) => (
              <div key={item} className="rounded-2xl bg-secondary/40 px-3 py-2 text-sm">{item}</div>
            ))}
          </div>
          <button className="mt-4 w-full rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={onContinueChat}>
            回到聊天
          </button>
        </div>
      )
  }
}
