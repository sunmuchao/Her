'use client'

import { Button } from '@/components/ui/button'
import { ArrowRight, Lightbulb } from 'lucide-react'
import { cn } from '@/lib/utils'
import { type AssessmentType } from './assessment-themes'

interface FeedbackData {
  dimension?: string
  dimension_name?: string
  score?: number
  feedback_text?: string
}

// MBTI Dimension configs (fallback)
const MBTI_DIMENSION_CONFIG: Record<string, { icon: string; color: string; bgColor: string; label: string }> = {
  EI: { icon: 'EI', color: 'text-rose', bgColor: 'bg-rose-soft', label: '社交能量' },
  SN: { icon: 'SN', color: 'text-gold', bgColor: 'bg-gold-soft', label: '信息感知' },
  TF: { icon: 'TF', color: 'text-primary', bgColor: 'bg-primary/10', label: '决策方式' },
  JP: { icon: 'JP', color: 'text-taupe', bgColor: 'bg-secondary', label: '生活态度' },
}

// Attachment Style dimension configs
const ATTACHMENT_DIMENSION_CONFIG: Record<string, { icon: string; color: string; bgColor: string; label: string }> = {
  anxiety: { icon: 'AX', color: 'text-coral', bgColor: 'bg-coral-soft', label: '焦虑维度' },
  avoidance: { icon: 'AV', color: 'text-rose', bgColor: 'bg-rose-soft', label: '回避维度' },
  security: { icon: 'SE', color: 'text-sage', bgColor: 'bg-sage-soft', label: '安全维度' },
  trust: { icon: 'TR', color: 'text-gold', bgColor: 'bg-gold-soft', label: '信任维度' },
}

// Love Language dimension configs
const LOVE_LANGUAGE_DIMENSION_CONFIG: Record<string, { icon: string; color: string; bgColor: string; label: string }> = {
  words: { icon: 'WD', color: 'text-lavender', bgColor: 'bg-lavender-soft', label: '肯定言词' },
  time: { icon: 'TM', color: 'text-sage', bgColor: 'bg-sage-soft', label: '精心时刻' },
  gifts: { icon: 'GF', color: 'text-gold', bgColor: 'bg-gold-soft', label: '接受礼物' },
  service: { icon: 'SV', color: 'text-coral', bgColor: 'bg-coral-soft', label: '服务行动' },
  touch: { icon: 'TC', color: 'text-rose', bgColor: 'bg-rose-soft', label: '身体接触' },
}

function getDimensionConfig(dimension?: string, assessmentType?: AssessmentType) {
  if (!dimension) {
    return undefined
  }

  if (assessmentType === 'attachment_style') {
    return ATTACHMENT_DIMENSION_CONFIG[dimension.toLowerCase()]
  }
  if (assessmentType === 'love_language') {
    return LOVE_LANGUAGE_DIMENSION_CONFIG[dimension.toLowerCase()]
  }
  return MBTI_DIMENSION_CONFIG[dimension]
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

function getScoreLevel(score: number, assessmentType?: AssessmentType): { label: string; color: string } {
  if (assessmentType === 'attachment_style') {
    if (score >= 70) return { label: '高', color: 'text-coral' }
    if (score >= 40) return { label: '中', color: 'text-sage' }
    return { label: '低', color: 'text-taupe' }
  }
  if (assessmentType === 'love_language') {
    if (score >= 70) return { label: '强', color: 'text-lavender' }
    if (score >= 40) return { label: '中', color: 'text-sage' }
    return { label: '弱', color: 'text-taupe' }
  }
  // MBTI default
  if (score >= 70) return { label: '高', color: 'text-rose' }
  if (score >= 40) return { label: '中', color: 'text-gold' }
  return { label: '低', color: 'text-taupe' }
}

export function AssessmentFeedbackCard({
  data,
  onContinue,
  assessmentType,
}: {
  data: FeedbackData
  onContinue: () => void
  assessmentType?: AssessmentType
}) {
  const safeScore = typeof data.score === 'number' ? data.score : 0
  const fallbackLabel = data.dimension_name || data.dimension || '阶段反馈'
  const fallbackIcon = (data.dimension || data.dimension_name || '--').slice(0, 2).toUpperCase()

  const config = getDimensionConfig(data.dimension, assessmentType) || {
    icon: fallbackIcon,
    color: assessmentType === 'attachment_style' ? 'text-coral' : 
           assessmentType === 'love_language' ? 'text-lavender' : 'text-primary',
    bgColor: assessmentType === 'attachment_style' ? 'bg-coral-soft' : 
             assessmentType === 'love_language' ? 'bg-lavender-soft' : 'bg-secondary',
    label: fallbackLabel,
  }
  
  const scoreLevel = getScoreLevel(safeScore, assessmentType)
  
  // Button color based on theme
  const buttonClass = assessmentType === 'attachment_style' 
    ? 'bg-coral hover:bg-coral/90 text-white' 
    : assessmentType === 'love_language' 
      ? 'bg-lavender hover:bg-lavender/90 text-white' 
      : ''

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
      {/* Header */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
        <Lightbulb className={cn(
          'w-4 h-4',
          assessmentType === 'attachment_style' ? 'text-coral' : 
          assessmentType === 'love_language' ? 'text-lavender' : ''
        )} />
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
          <h3 className="text-xl font-semibold">{fallbackLabel}</h3>
          <span className={cn('text-sm', scoreLevel.color)}>
            {scoreLevel.label}{"倾向"}
          </span>
        </div>
      </div>

      {/* Circular Progress */}
      <div className="flex justify-center my-6">
        <CircularProgress 
          score={safeScore} 
          size={120} 
          strokeWidth={10}
          colorClass={config.color}
        />
      </div>

      {/* Feedback Text */}
      <div className={cn(
        'rounded-2xl p-4',
        assessmentType === 'attachment_style' ? 'bg-coral-soft/40' : 
        assessmentType === 'love_language' ? 'bg-lavender-soft/40' : 'bg-secondary/40'
      )}>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {data.feedback_text || '结果已生成，继续查看下一维度。'}
        </p>
      </div>

      {/* Continue Button */}
      <Button
        className={cn('mt-5 w-full h-12 rounded-xl text-base font-medium group', buttonClass)}
        onClick={onContinue}
      >
        <span>{"继续探索下一维度"}</span>
        <ArrowRight className="w-4 h-4 ml-1 transition-transform group-hover:translate-x-1" />
      </Button>
    </div>
  )
}
