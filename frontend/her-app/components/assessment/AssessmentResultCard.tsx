'use client'

export function AssessmentResultCard({
  data,
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
    interpretation_data: {
      summary: string
      love_style: string
      match_suggestions: string[]
    }
    reward: string
  }
}) {
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
      <div className="mt-5 rounded-2xl bg-secondary/40 p-4">
        <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">AI 解读</div>
        <p className="mt-3 text-sm leading-relaxed">{data.interpretation_data.summary}</p>
        <p className="mt-3 text-sm text-muted-foreground">{data.interpretation_data.love_style}</p>
        <div className="mt-4 space-y-2">
          {data.interpretation_data.match_suggestions.map((item) => (
            <div key={item} className="rounded-2xl bg-background px-3 py-2 text-sm">
              {item}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
