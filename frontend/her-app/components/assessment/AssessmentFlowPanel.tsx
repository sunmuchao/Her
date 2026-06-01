'use client'

import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  answerAssessment,
  beginAssessment,
  type AssessmentCard,
  type AssessmentQuestionCard,
  getOrCreateAssessment,  // 改用新的断点续传API
  addAssessmentLabels,     // 新增：添加标签API
} from '@/lib/api/endpoints/assessment'

import { AssessmentCardRenderer } from './AssessmentCardRenderer'

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

  useEffect(() => {
    if (!open) return
    let cancelled = false

    // 改用 getOrCreateAssessment（自动恢复或新建）
    // 防呆机制：用户退出App后，下次进来能接着上次的进度继续做
    void getOrCreateAssessment(userKey).then((intro) => {
      if (cancelled) return
      setAssessmentId(intro.assessment_id)
      setCard(intro)
      setQuestionHistory([])

      // 如果是恢复的测评，可以显示提示（可选）
      if (intro.resumed) {
        console.log(`恢复测评：已答 ${intro.answered_count} 题`)
      }
    })

    return () => {
      cancelled = true
    }
  }, [open, userKey])

  const loading = useMemo(() => open && !card, [open, card])

  if (!open) return null

  const close = () => {
    setCard(null)
    setAssessmentId(null)
    onClose()
  }

  // 添加标签到个人标签
  const handleAddLabels = async (selectedLabels: string[]) => {
    await addAssessmentLabels(userKey, selectedLabels)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-3">
      <div className="w-full max-w-lg rounded-[28px] bg-background p-3 shadow-2xl">
        <div className="mb-3 flex items-center justify-between px-2">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">人格测评</div>
            <div className="text-sm text-muted-foreground">MBTI 16 型</div>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={close}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        {loading && <div className="rounded-3xl border border-border bg-card p-5 text-sm text-muted-foreground">加载中…</div>}
        {card && assessmentId && (
          <AssessmentCardRenderer
            card={card}
            onStart={async () => {
              const next = await beginAssessment(assessmentId)
              setCard(next)
            }}
            onAnswer={async (answer) => {
              if (card.card_type !== 'assessment_question') return
              setQuestionHistory((prev) => [...prev, card.question_data])
              const next = await answerAssessment({
                assessmentId,
                questionIndex: card.question_data.current_question - 1,
                answer,
                userKey,
              })
              setCard(next)
            }}
            onContinue={async () => {
              if (card.card_type !== 'assessment_feedback') return
              setCard({ card_type: 'assessment_question', assessment_id: assessmentId, question_data: card.next_question })
            }}
            onContinueChat={close}
            onPrevious={
              questionHistory.length > 0
                ? () => {
                    const previous = questionHistory[questionHistory.length - 1]
                    setQuestionHistory((prev) => prev.slice(0, -1))
                    setCard({ card_type: 'assessment_question', assessment_id: assessmentId, question_data: previous })
                  }
                : undefined
            }
            onAddLabels={handleAddLabels}
          />
        )}
      </div>
    </div>
  )
}
