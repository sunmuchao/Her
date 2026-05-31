'use client'

import { Button } from '@/components/ui/button'

export function AssessmentQuestionCard({
  data,
  onAnswer,
  onPrevious,
}: {
  data: {
    current_question: number
    total_questions: number
    question_text: string
    options: Array<{ label: string; text: string; score: number }>
    progress: number
  }
  onAnswer: (answer: string) => void
  onPrevious?: () => void
}) {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-4 space-y-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>第 {data.current_question} / {data.total_questions} 题</span>
          <span>{data.progress}%</span>
        </div>
        <div className="h-2 rounded-full bg-secondary">
          <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${data.progress}%` }} />
        </div>
      </div>
      <h3 className="text-lg font-semibold leading-snug">{data.question_text}</h3>
      <div className="mt-4 grid gap-2">
        {data.options.map((option) => (
          <Button key={option.label} variant="outline" className="justify-start h-auto py-3 px-4" onClick={() => onAnswer(option.label)}>
            <span className="w-6 text-left font-medium">{option.label}</span>
            <span>{option.text}</span>
          </Button>
        ))}
      </div>
      {onPrevious && (
        <Button variant="ghost" className="mt-3 w-full" onClick={onPrevious}>上一题</Button>
      )}
    </div>
  )
}
