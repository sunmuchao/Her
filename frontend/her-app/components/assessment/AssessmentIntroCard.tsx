'use client'

import { Button } from '@/components/ui/button'
import { Heart, Clock, Sparkles, ArrowRight, Brain, Link2, MessageCircleHeart } from 'lucide-react'
import { cn } from '@/lib/utils'
import { type AssessmentType, getAssessmentTheme } from './assessment-themes'

interface IntroData {
  title: string
  description: string
  duration: string
  reward: string
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
  const theme = getAssessmentTheme(assessmentType)
  
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
      {/* Animated Icon with Radar Effect - Theme Specific */}
      <div className="relative flex justify-center mb-5">
        <div className="relative">
          {/* Pulse rings - using theme colors */}
          <div 
            className={cn(
              'absolute inset-0 rounded-full animate-ping-slow',
              assessmentType === 'attachment_style' ? 'bg-coral/20' :
              assessmentType === 'love_language' ? 'bg-lavender/20' : 'bg-rose/20'
            )} 
            style={{ animationDelay: '0ms' }} 
          />
          <div 
            className={cn(
              'absolute inset-0 rounded-full animate-ping-slow',
              assessmentType === 'attachment_style' ? 'bg-coral/10' :
              assessmentType === 'love_language' ? 'bg-lavender/10' : 'bg-rose/10'
            )} 
            style={{ animationDelay: '500ms' }} 
          />
          
          {/* Main icon container - theme gradient */}
          <div className={cn(
            'relative flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br',
            theme.gradientFrom,
            theme.gradientTo
          )}>
            <ThemeIcon 
              iconType={theme.iconType} 
              className={cn(
                'w-9 h-9 animate-heartbeat',
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

      {/* Resume Indicator - Theme Colored */}
      {isResumed && answeredCount > 0 && (
        <div className={cn(
          'mt-4 flex items-center justify-center gap-2 px-4 py-2 rounded-full border',
          assessmentType === 'attachment_style' ? 'bg-coral-soft/50 border-coral/20' :
          assessmentType === 'love_language' ? 'bg-lavender-soft/50 border-lavender/20' : 
          'bg-gold-soft/50 border-gold/20'
        )}>
          <Sparkles className={cn(
            'w-4 h-4',
            assessmentType === 'attachment_style' ? 'text-coral' :
            assessmentType === 'love_language' ? 'text-lavender' : 'text-gold'
          )} />
          <span className="text-sm text-taupe">
            {"继续上次进度 - 已答 "}{answeredCount}{" 题"}
          </span>
        </div>
      )}

      {/* Info Cards */}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Clock className="w-5 h-5 text-muted-foreground" />
          </div>
          <div>
            <div className="text-xs text-muted-foreground">{"预计时长"}</div>
            <div className="text-sm font-medium">{data.duration}</div>
          </div>
        </div>
        
        <div className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Sparkles className={cn(
              'w-5 h-5',
              assessmentType === 'attachment_style' ? 'text-coral' :
              assessmentType === 'love_language' ? 'text-lavender' : 'text-gold'
            )} />
          </div>
          <div>
            <div className="text-xs text-muted-foreground">{"完成奖励"}</div>
            <div className="text-sm font-medium">{data.reward}</div>
          </div>
        </div>
      </div>

      {/* Start Button - Theme Colored */}
      <Button
        className={cn(
          'mt-5 w-full h-12 rounded-xl text-base font-medium group',
          assessmentType === 'attachment_style' ? 'bg-coral hover:bg-coral/90 text-white' :
          assessmentType === 'love_language' ? 'bg-lavender hover:bg-lavender/90 text-white' : ''
        )}
        onClick={onStart}
      >
        <span>{isResumed ? '继续测评' : '开始测试'}</span>
        <ArrowRight className="w-4 h-4 ml-1 transition-transform group-hover:translate-x-1" />
      </Button>
    </div>
  )
}
