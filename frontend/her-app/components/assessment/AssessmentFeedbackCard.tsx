'use client'

import { useEffect } from 'react'

export function AssessmentFeedbackCard({
  data,
  onContinue,
}: {
  data: {
    dimension_name: string
    score: number
    feedback_text: string
  }
  onContinue: () => void
}) {
  useEffect(() => {
    const timer = setTimeout(onContinue, 2000)
    return () => clearTimeout(timer)
  }, [onContinue])

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
      <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">阶段反馈</div>
      <div className="mt-2 flex items-end gap-3">
        <h3 className="text-xl font-semibold">{data.dimension_name}</h3>
        <span className="text-sm text-muted-foreground">{data.score.toFixed(1)}</span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{data.feedback_text}</p>
      <p className="mt-4 text-xs text-muted-foreground">正在进入下一题…</p>
    </div>
  )
}
