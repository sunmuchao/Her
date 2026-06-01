'use client'

import { Button } from '@/components/ui/button'
import { ArrowRight, Lightbulb } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FeedbackData {
  dimension: string
  dimension_name: string
  score: number
  feedback_text: string
}

// Dimension icons and colors
const DIMENSION_CONFIG: Record<string, { icon: string; color: string; bgColor: string; label: string }> = {
  EI: { icon: 'EI', color: 'text-rose', bgColor: 'bg-rose-soft', label: '社交能量' },
  SN: { icon: 'SN', color: 'text-gold', bgColor: 'bg-gold-soft', label: '信息感知' },
  TF: { icon: 'TF', color: 'text-primary', bgColor: 'bg-primary/10', label: '决策方式' },
  JP: { icon: 'JP', color: 'text-taupe', bgColor: 'bg-secondary', label: '生活态度' },
}

function CircularProgress({ 
  score, 
  size = 100, 
  strokeWidth = 8,
  colorClass = 'text-primary'
}: { 
  score: number
  size?: number
  strokeWidth?: number
  colorClass?: string
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const offset = circumference - (score / 100) * circumference
  
  return (
    <div className="relative" style={{ width: size, height: size }}>
      {/* Background circle */}
      <svg className="transform -rotate-90" width={size} height={size}>
        <circle
          className="text-secondary"
          strokeWidth={strokeWidth}
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        {/* Progress circle */}
        <circle
          className={cn('transition-all duration-1000 ease-out', colorClass)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          style={{
            '--progress-offset': offset,
          } as React.CSSProperties}
        />
      </svg>
      {/* Center content */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold">{score.toFixed(0)}</span>
        <span className="text-xs text-muted-foreground">{"分"}</span>
      </div>
    </div>
  )
}

function getScoreLevel(score: number): { label: string; color: string } {
  if (score >= 70) return { label: '高', color: 'text-rose' }
  if (score >= 40) return { label: '中', color: 'text-gold' }
  return { label: '低', color: 'text-taupe' }
}

export function AssessmentFeedbackCard({
  data,
  onContinue,
}: {
  data: FeedbackData
  onContinue: () => void
}) {
  const config = DIMENSION_CONFIG[data.dimension] || {
    icon: data.dimension,
    color: 'text-primary',
    bgColor: 'bg-secondary',
    label: data.dimension_name,
  }
  
  const scoreLevel = getScoreLevel(data.score)

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
      {/* Header */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
        <Lightbulb className="w-4 h-4" />
        <span className="uppercase tracking-widest">{"小发现"}</span>
      </div>

      {/* Dimension Title */}
      <div className="flex items-center gap-3 mb-5">
        <div className={cn(
          'flex items-center justify-center w-12 h-12 rounded-2xl font-semibold text-sm',
          config.bgColor,
          config.color
        )}>
          {config.icon}
        </div>
        <div>
          <h3 className="text-xl font-semibold">{data.dimension_name}</h3>
          <span className={cn('text-sm', scoreLevel.color)}>
            {scoreLevel.label}{"倾向"}
          </span>
        </div>
      </div>

      {/* Circular Progress */}
      <div className="flex justify-center my-6">
        <CircularProgress 
          score={data.score} 
          size={120} 
          strokeWidth={10}
          colorClass={config.color}
        />
      </div>

      {/* Feedback Text */}
      <div className="rounded-2xl bg-secondary/40 p-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {data.feedback_text}
        </p>
      </div>

      {/* Continue Button */}
      <Button
        className="mt-5 w-full h-12 rounded-xl text-base font-medium group"
        onClick={onContinue}
      >
        <span>{"继续探索下一维度"}</span>
        <ArrowRight className="w-4 h-4 ml-1 transition-transform group-hover:translate-x-1" />
      </Button>
    </div>
  )
}
