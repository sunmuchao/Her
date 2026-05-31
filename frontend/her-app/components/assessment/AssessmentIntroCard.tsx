'use client'

import { Button } from '@/components/ui/button'

export function AssessmentIntroCard({
  data,
  onStart,
}: {
  data: {
    title: string
    description: string
    duration: string
    reward: string
  }
  onStart: () => void
}) {
  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
      <div className="space-y-2">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">人格测评</p>
        <h3 className="text-xl font-semibold">{data.title}</h3>
        <p className="text-sm text-muted-foreground">{data.description}</p>
      </div>
      <div className="mt-4 grid gap-2 rounded-2xl bg-secondary/40 p-4 text-sm">
        <div className="flex justify-between"><span>时长</span><span>{data.duration}</span></div>
        <div className="flex justify-between"><span>奖励</span><span>{data.reward}</span></div>
      </div>
      <Button className="mt-4 w-full" onClick={onStart}>开始测评</Button>
    </div>
  )
}
