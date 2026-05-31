'use client'

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
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
      <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">阶段反馈</div>
      <div className="mt-2 flex items-end gap-3">
        <h3 className="text-xl font-semibold">{data.dimension_name}</h3>
        <span className="text-sm text-muted-foreground">{data.score.toFixed(0)}%</span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{data.feedback_text}</p>
      <button
        className="mt-4 w-full rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
        onClick={onContinue}
      >
        下一题
      </button>
    </div>
  )
}
