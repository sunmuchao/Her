'use client'

import { useEffect } from 'react'
import { Button } from '@/components/ui/button'

export function AssessmentResultCard({
  data,
  onInterpretation,
  onContinueChat,
}: {
  data: {
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
  }
  onInterpretation: () => void
  onContinueChat: () => void
}) {
  useEffect(() => {
    const timer = setTimeout(onInterpretation, 2000)
    return () => clearTimeout(timer)
  }, [onInterpretation])

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
      <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">测评结果</div>
      <div className="mt-2 text-2xl font-semibold">{data.type_code}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {data.labels.map((label) => (
          <span key={label} className="rounded-full bg-secondary px-3 py-1 text-xs">{label}</span>
        ))}
      </div>
      <div className="mt-4 grid gap-3">
        {data.dimension_rows.map((row) => (
          <div key={row.key}>
            <div className="mb-1 flex justify-between text-sm">
              <span>{row.name}</span>
              <span>{row.score.toFixed(1)}</span>
            </div>
            <div className="h-2 rounded-full bg-secondary">
              <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${row.score}%` }} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-muted-foreground">{data.reward}</p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Button variant="outline" onClick={onInterpretation}>查看解读</Button>
        <Button onClick={onContinueChat}>继续聊天</Button>
      </div>
    </div>
  )
}
