'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Heart, Clock, Sparkles, ArrowRight, Brain, Link2, MessageCircleHeart, Play } from 'lucide-react'
import { cn } from '@/lib/utils'
import { type AssessmentType, getAssessmentTheme } from './assessment-themes'
import { RingBurst, useHapticFeedback } from './immersive-effects'

interface IntroData {
  title: string
  description: string
  duration: string
  reward: string
  totalQuestions?: number
}

// Icon component based on theme
function ThemeIcon({ 
  iconType, 
  className 
}: { 
  iconType: 'brain' | 'heart' | 'sparkles' | 'link' | 'message-heart'
  className?: string 
}) {
  switch (iconType) {
    case 'brain':
      return <Brain className={className} />
    case 'link':
      return <Link2 className={className} />
    case 'message-heart':
      return <MessageCircleHeart className={className} />
    case 'sparkles':
      return <Sparkles className={className} />
    case 'heart':
    default:
      return <Heart className={className} fill="currentColor" />
  }
}

export function AssessmentIntroCard({
  data,
  onStart,
  isResumed = false,
  answeredCount = 0,
  assessmentType,
}: {
  data: IntroData
  onStart: () => void
  isResumed?: boolean
  answeredCount?: number
  assessmentType?: AssessmentType
}) {
  const [isStarting, setIsStarting] = useState(false)
  const [showBurst, setShowBurst] = useState(false)
  const haptic = useHapticFeedback()
  
  const theme = getAssessmentTheme(assessmentType)
  const totalQuestions = data.totalQuestions || theme.questionCount
  const progressPercent = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0
  
  const handleStart = () => {
    setIsStarting(true)
    setShowBurst(true)
    haptic('success')
    
    // Delay to show the burst animation
    setTimeout(() => {
      onStart()
    }, 400)
  }
  
  const themeColor = assessmentType === 'attachment_style' ? 'var(--coral)' :
                     assessmentType === 'love_language' ? 'var(--lavender)' : 'var(--primary)'
  
  return (
    <div className={cn(
      'rounded-3xl border border-border bg-card p-6 shadow-sm',
      isStarting ? 'animate-card-flip-out' : 'animate-scale-in'
    )}>
      {/* Animated Icon with Radar Effect - Theme Specific */}
      <div className="relative flex justify-center mb-5">
        <div className="relative will-change-transform">
          {/* Ring burst on start */}
          <RingBurst trigger={showBurst} color={themeColor} rings={3} />
          
          {/* Pulse rings */}
          <div 
            className={cn(
              'absolute inset-0 rounded-full animate-ping-slow will-change-transform',
              assessmentType === 'attachment_style' ? 'bg-coral/15' :
              assessmentType === 'love_language' ? 'bg-lavender/15' : 'bg-rose/15'
            )} 
          />
          
          {/* Main icon container - theme gradient */}
          <div className={cn(
            'relative flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br transition-transform duration-300',
            theme.gradientFrom,
            theme.gradientTo,
            isStarting && 'scale-110'
          )}>
            <ThemeIcon 
              iconType={theme.iconType} 
              className={cn(
                'w-9 h-9 animate-heartbeat will-change-transform',
                assessmentType === 'attachment_style' ? 'text-coral' :
                assessmentType === 'love_language' ? 'text-lavender' : 'text-rose'
              )} 
            />
          </div>
        </div>
      </div>

      {/* Title and Description */}
      <div className="text-center space-y-2">
        <h3 className="text-xl font-semibold text-balance">{data.title}</h3>
        <p className="text-sm text-muted-foreground leading-relaxed text-pretty">
          {data.description}
        </p>
      </div>

      {/* Resume Indicator with Progress Bar - Theme Colored */}
      {isResumed && answeredCount > 0 && (
        <div className={cn(
          'mt-4 px-4 py-3 rounded-2xl border',
          assessmentType === 'attachment_style' ? 'bg-coral-soft/50 border-coral/20' :
          assessmentType === 'love_language' ? 'bg-lavender-soft/50 border-lavender/20' : 
          'bg-gold-soft/50 border-gold/20'
        )}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Sparkles className={cn(
                'w-4 h-4',
                assessmentType === 'attachment_style' ? 'text-coral' :
                assessmentType === 'love_language' ? 'text-lavender' : 'text-gold'
              )} />
              <span className="text-sm text-foreground font-medium">{"继续上次进度"}</span>
            </div>
            <span className="text-xs text-muted-foreground">
              {answeredCount}/{totalQuestions} {"题"}
            </span>
          </div>
          {/* Progress bar visualization */}
          <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
            <div 
              className={cn(
                'h-full rounded-full transition-all duration-500',
                assessmentType === 'attachment_style' ? 'bg-coral' :
                assessmentType === 'love_language' ? 'bg-lavender' : 'bg-gold'
              )}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {/* Info Cards */}
      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex items-start gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Clock className="w-5 h-5 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{"预计时长"}</div>
            <div className="text-sm font-medium leading-snug break-words">{data.duration}</div>
          </div>
        </div>
        
        <div className="flex items-start gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Sparkles className={cn(
              'w-5 h-5',
              assessmentType === 'attachment_style' ? 'text-coral' :
              assessmentType === 'love_language' ? 'text-lavender' : 'text-gold'
            )} />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{"完成奖励"}</div>
            <div className="text-sm font-medium leading-snug break-words">{data.reward}</div>
          </div>
        </div>
      </div>

      {/* Start Button - Theme Colored with enhanced interaction */}
      <Button
        className={cn(
          'mt-5 w-full h-14 rounded-xl text-base font-semibold group touch-target relative overflow-hidden',
          'transition-all duration-300 active:scale-[0.97]',
          assessmentType === 'attachment_style' ? 'bg-coral hover:bg-coral/90 text-white' :
          assessmentType === 'love_language' ? 'bg-lavender hover:bg-lavender/90 text-white' : '',
          isStarting && 'scale-105'
        )}
        onClick={handleStart}
        disabled={isStarting}
      >
        {/* Shimmer effect */}
        <span className="absolute inset-0 overflow-hidden">
          <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/20 to-transparent group-hover:animate-shimmer-sweep" />
        </span>
        
        <span className="relative flex items-center justify-center gap-2">
          {isStarting ? (
            <>
              <Play className="w-5 h-5 animate-pulse" fill="currentColor" />
              <span>{"准备中..."}</span>
            </>
          ) : (
            <>
              <span>{isResumed ? '继续测评' : '开始探索'}</span>
              <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
            </>
          )}
        </span>
      </Button>
    </div>
  )
}
