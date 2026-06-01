'use client'

import { Button } from '@/components/ui/button'
import { Heart, Clock, Sparkles, ArrowRight } from 'lucide-react'

interface IntroData {
  title: string
  description: string
  duration: string
  reward: string
}

export function AssessmentIntroCard({
  data,
  onStart,
  isResumed = false,
  answeredCount = 0,
}: {
  data: IntroData
  onStart: () => void
  isResumed?: boolean
  answeredCount?: number
}) {
  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
      {/* Animated Heart Icon with Radar Effect */}
      <div className="relative flex justify-center mb-5">
        <div className="relative">
          {/* Pulse rings */}
          <div className="absolute inset-0 rounded-full bg-rose/20 animate-ping-slow" style={{ animationDelay: '0ms' }} />
          <div className="absolute inset-0 rounded-full bg-rose/10 animate-ping-slow" style={{ animationDelay: '500ms' }} />
          
          {/* Main icon container */}
          <div className="relative flex items-center justify-center w-20 h-20 rounded-full bg-gradient-to-br from-rose-soft to-gold-soft">
            <Heart className="w-9 h-9 text-rose animate-heartbeat" fill="currentColor" />
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

      {/* Resume Indicator */}
      {isResumed && answeredCount > 0 && (
        <div className="mt-4 flex items-center justify-center gap-2 px-4 py-2 rounded-full bg-gold-soft/50 border border-gold/20">
          <Sparkles className="w-4 h-4 text-gold" />
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
            <Sparkles className="w-5 h-5 text-gold" />
          </div>
          <div>
            <div className="text-xs text-muted-foreground">{"完成奖励"}</div>
            <div className="text-sm font-medium">{data.reward}</div>
          </div>
        </div>
      </div>

      {/* MBTI Dimensions Preview */}
      <div className="mt-5 grid grid-cols-4 gap-2">
        {[
          { label: 'E/I', name: '社交' },
          { label: 'S/N', name: '感知' },
          { label: 'T/F', name: '决策' },
          { label: 'J/P', name: '生活' },
        ].map((dim) => (
          <div
            key={dim.label}
            className="flex flex-col items-center justify-center py-2 px-1 rounded-xl bg-muted/50 text-center"
          >
            <span className="text-xs font-medium text-foreground">{dim.label}</span>
            <span className="text-[10px] text-muted-foreground">{dim.name}</span>
          </div>
        ))}
      </div>

      {/* Start Button */}
      <Button
        className="mt-5 w-full h-12 rounded-xl text-base font-medium group"
        onClick={onStart}
      >
        <span>{isResumed ? '继续测评' : '开始测试'}</span>
        <ArrowRight className="w-4 h-4 ml-1 transition-transform group-hover:translate-x-1" />
      </Button>

      {/* Footer hint */}
      <p className="mt-3 text-center text-xs text-muted-foreground">
        {"答案无对错之分，请选择最符合你的选项"}
      </p>
    </div>
  )
}
