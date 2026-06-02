'use client'

import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { ArrowRight, Lightbulb, ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { type AssessmentType } from './assessment-themes'
import { useHapticFeedback, RingBurst } from './immersive-effects'

interface FeedbackData {
  dimension?: string
  dimension_name?: string
  score?: number
  feedback_text?: string
}

const LOVE_LANGUAGE_LABELS: Record<string, string> = {
  words_of_affirmation: '肯定言词',
  quality_time: '精心时刻',
  receiving_gifts: '接受礼物',
  acts_of_service: '服务行动',
  physical_touch: '身体接触',
  words: '肯定言词',
  time: '精心时刻',
  gifts: '接受礼物',
  service: '服务行动',
  touch: '身体接触',
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
  words_of_affirmation: { icon: 'WD', color: 'text-lavender', bgColor: 'bg-lavender-soft', label: '肯定言词' },
  quality_time: { icon: 'TM', color: 'text-sage', bgColor: 'bg-sage-soft', label: '精心时刻' },
  receiving_gifts: { icon: 'GF', color: 'text-gold', bgColor: 'bg-gold-soft', label: '接受礼物' },
  acts_of_service: { icon: 'SV', color: 'text-coral', bgColor: 'bg-coral-soft', label: '服务行动' },
  physical_touch: { icon: 'TC', color: 'text-rose', bgColor: 'bg-rose-soft', label: '身体接触' },
  words: { icon: 'WD', color: 'text-lavender', bgColor: 'bg-lavender-soft', label: '肯定言词' },
  time: { icon: 'TM', color: 'text-sage', bgColor: 'bg-sage-soft', label: '精心时刻' },
  gifts: { icon: 'GF', color: 'text-gold', bgColor: 'bg-gold-soft', label: '接受礼物' },
  service: { icon: 'SV', color: 'text-coral', bgColor: 'bg-coral-soft', label: '服务行动' },
  touch: { icon: 'TC', color: 'text-rose', bgColor: 'bg-rose-soft', label: '身体接触' },
}

function normalizeDimensionKey(dimension?: string) {
  return dimension?.trim().toLowerCase()
}

function getDimensionLabel(data: FeedbackData, assessmentType?: AssessmentType) {
  if (data.dimension_name?.trim()) {
    return data.dimension_name.trim()
  }

  const normalizedDimension = normalizeDimensionKey(data.dimension)
  if (!normalizedDimension) {
    return '阶段反馈'
  }

  if (assessmentType === 'love_language') {
    return LOVE_LANGUAGE_LABELS[normalizedDimension] || data.dimension || '阶段反馈'
  }

  const config = getDimensionConfig(normalizedDimension, assessmentType)
  return config?.label || data.dimension || '阶段反馈'
}

function getDimensionConfig(dimension?: string, assessmentType?: AssessmentType) {
  const normalizedDimension = normalizeDimensionKey(dimension)
  if (!normalizedDimension) {
    return undefined
  }

  if (assessmentType === 'attachment_style') {
    return ATTACHMENT_DIMENSION_CONFIG[normalizedDimension]
  }
  if (assessmentType === 'love_language') {
    return LOVE_LANGUAGE_DIMENSION_CONFIG[normalizedDimension]
  }
  return MBTI_DIMENSION_CONFIG[dimension?.trim() || '']
}

// Animated circular progress with reveal effect
function CircularProgressReveal({ 
  score, 
  size = 140, 
  strokeWidth = 10,
  colorClass = 'text-primary',
  glowClass = 'glow-primary',
}: { 
  score: number
  size?: number
  strokeWidth?: number
  colorClass?: string
  glowClass?: string
}) {
  const [phase, setPhase] = useState<'hidden' | 'revealing' | 'counting' | 'complete'>('hidden')
  const [displayedScore, setDisplayedScore] = useState(0)
  const [progressPercent, setProgressPercent] = useState(0)
  const haptic = useHapticFeedback()
  
  const radius = (size - strokeWidth) / 2
  const circumference = radius * 2 * Math.PI
  const offset = circumference - (progressPercent / 100) * circumference
  
  // Animation sequence
  useEffect(() => {
    // Phase 1: Reveal
    const revealTimer = setTimeout(() => {
      setPhase('revealing')
      haptic('light')
    }, 200)
    
    // Phase 2: Start counting
    const countTimer = setTimeout(() => {
      setPhase('counting')
    }, 600)
    
    // Phase 3: Animate score and progress together
    const animateTimer = setTimeout(() => {
      const duration = 1200
      const startTime = Date.now()
      
      const animate = () => {
        const elapsed = Date.now() - startTime
        const progress = Math.min(elapsed / duration, 1)
        
        // Easing function (ease-out cubic)
        const eased = 1 - Math.pow(1 - progress, 3)
        
        setDisplayedScore(Math.round(score * eased))
        setProgressPercent(score * eased)
        
        if (progress < 1) {
          requestAnimationFrame(animate)
        } else {
          setPhase('complete')
          haptic('success')
        }
      }
      
      requestAnimationFrame(animate)
    }, 700)
    
    return () => {
      clearTimeout(revealTimer)
      clearTimeout(countTimer)
      clearTimeout(animateTimer)
    }
  }, [score, haptic])
  
  return (
    <div 
      className={cn(
        'relative transition-all duration-500',
        phase === 'hidden' && 'opacity-0 scale-75 blur-md',
        phase === 'revealing' && 'opacity-100 scale-100 blur-0 animate-score-reveal',
        phase === 'complete' && glowClass
      )} 
      style={{ width: size, height: size }}
    >
      {/* Background glow */}
      {phase === 'complete' && (
        <div className={cn(
          'absolute inset-0 rounded-full opacity-30 blur-xl animate-ambient-pulse',
          colorClass
        )} />
      )}
      
      {/* SVG Progress */}
      <svg className="transform -rotate-90 relative z-10" width={size} height={size}>
        {/* Background circle */}
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
          className={cn('transition-all duration-100 ease-out', colorClass)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
      </svg>
      
      {/* Center content */}
      <div className="absolute inset-0 flex flex-col items-center justify-center z-20">
        <span className={cn(
          'text-4xl font-bold tabular-nums transition-all duration-300',
          phase === 'complete' && 'animate-elastic-pop'
        )}>
          {displayedScore}
        </span>
        <span className="text-sm text-muted-foreground mt-1">{"分"}</span>
      </div>
      
      {/* Ring burst on complete */}
      <RingBurst 
        trigger={phase === 'complete'} 
        color={`var(${colorClass.includes('coral') ? '--coral' : colorClass.includes('lavender') ? '--lavender' : '--primary'})`}
        rings={2}
      />
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
  const [isTextExpanded, setIsTextExpanded] = useState(false)
  const [showContent, setShowContent] = useState(false)
  const safeScore = typeof data.score === 'number' ? data.score : 0
  const fallbackLabel = getDimensionLabel(data, assessmentType)
  const fallbackIcon = (fallbackLabel || '--').slice(0, 2).toUpperCase()

  const config = getDimensionConfig(data.dimension, assessmentType) || {
    icon: fallbackIcon,
    color: assessmentType === 'attachment_style' ? 'text-coral' : 
           assessmentType === 'love_language' ? 'text-lavender' : 'text-primary',
    bgColor: assessmentType === 'attachment_style' ? 'bg-coral-soft' : 
             assessmentType === 'love_language' ? 'bg-lavender-soft' : 'bg-secondary',
    label: fallbackLabel,
  }
  
  const glowClass = assessmentType === 'attachment_style' ? 'glow-coral' : 
                    assessmentType === 'love_language' ? 'glow-lavender' : 'glow-primary'
  
  const scoreLevel = getScoreLevel(safeScore, assessmentType)
  
  // Button color based on theme
  const buttonClass = assessmentType === 'attachment_style' 
    ? 'bg-coral hover:bg-coral/90 text-white' 
    : assessmentType === 'love_language' 
      ? 'bg-lavender hover:bg-lavender/90 text-white' 
      : ''
  
  // Check if feedback text is long (more than ~100 chars)
  const feedbackText = data.feedback_text || '结果已生成，继续查看下一维度。'
  const isLongText = feedbackText.length > 100
  const shouldTruncate = isLongText && !isTextExpanded

  // Show content after score reveal
  useEffect(() => {
    const timer = setTimeout(() => setShowContent(true), 1800)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-card-flip-in perspective-1000">
      {/* Header */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4 animate-fade-in">
        <Sparkles className={cn(
          'w-4 h-4 animate-pulse-soft',
          assessmentType === 'attachment_style' ? 'text-coral' : 
          assessmentType === 'love_language' ? 'text-lavender' : 'text-primary'
        )} />
        <span className="uppercase tracking-widest">{"维度分析"}</span>
      </div>

      {/* Dimension Title */}
      <div className={cn(
        'flex items-center gap-3 mb-6 transition-all duration-500',
        showContent ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
      )}>
        <div className={cn(
          'flex items-center justify-center w-14 h-14 rounded-2xl font-bold text-base transition-transform duration-300',
          config.bgColor,
          config.color,
          showContent && 'animate-elastic-pop'
        )}>
          {config.icon}
        </div>
        <div>
          <h3 className="text-xl font-bold">{fallbackLabel}</h3>
          <span className={cn('text-sm font-medium', scoreLevel.color)}>
            {scoreLevel.label}{"倾向"}
          </span>
        </div>
      </div>

      {/* Circular Progress with Reveal Effect */}
      <div className="flex justify-center my-8">
        <CircularProgressReveal 
          score={safeScore} 
          size={150} 
          strokeWidth={12}
          colorClass={config.color}
          glowClass={glowClass}
        />
      </div>

      {/* Feedback Text with expandable support */}
      <div className={cn(
        'rounded-2xl p-4 transition-all duration-500',
        assessmentType === 'attachment_style' ? 'bg-coral-soft/40' : 
        assessmentType === 'love_language' ? 'bg-lavender-soft/40' : 'bg-secondary/40',
        showContent ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
      )}>
        <p className={cn(
          'text-sm leading-relaxed text-foreground/80 transition-all duration-300',
          shouldTruncate && 'line-clamp-3'
        )}>
          {feedbackText}
        </p>
        {isLongText && (
          <button
            onClick={() => setIsTextExpanded(!isTextExpanded)}
            className={cn(
              'mt-2 flex items-center gap-1 text-xs font-medium transition-colors touch-target',
              assessmentType === 'attachment_style' ? 'text-coral hover:text-coral/80' : 
              assessmentType === 'love_language' ? 'text-lavender hover:text-lavender/80' : 
              'text-primary hover:text-primary/80'
            )}
          >
            {isTextExpanded ? (
              <>
                <ChevronUp className="w-3.5 h-3.5" />
                {"收起"}
              </>
            ) : (
              <>
                <ChevronDown className="w-3.5 h-3.5" />
                {"展开全部"}
              </>
            )}
          </button>
        )}
      </div>

      {/* Continue Button */}
      <Button
        className={cn(
          'mt-5 w-full h-12 rounded-xl text-base font-medium group touch-target transition-all',
          'active:scale-[0.98]',
          buttonClass,
          showContent ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
        )}
        onClick={onContinue}
        style={{ transitionDelay: showContent ? '0ms' : '2000ms' }}
      >
        <span>{"继续探索下一维度"}</span>
        <ArrowRight className="w-4 h-4 ml-1 transition-transform group-hover:translate-x-1" />
      </Button>
    </div>
  )
}
