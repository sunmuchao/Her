/**
 * 价值观拍卖会介绍卡片
 */

import React from 'react'
import { Clock, Target, Gem, Gift, Coins, ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionIntroCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionIntroCard
  onStart: () => void
}

export function ValuesAuctionIntroCardComponent({ card, onStart }: Props) {
  const { intro_data } = card

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
      {/* Animated Icon with Radar Effect */}
      <div className="relative flex justify-center mb-5">
        <div className="relative will-change-transform">
          {/* Single optimized pulse ring */}
          <div className="absolute inset-0 rounded-full animate-ping-slow will-change-transform bg-amber/15" />
          
          {/* Main icon container */}
          <div className={cn(
            'relative flex items-center justify-center w-20 h-20 rounded-full',
            'bg-gradient-to-br from-amber-soft to-gold-soft'
          )}>
            <Coins className="w-9 h-9 text-amber animate-heartbeat will-change-transform" />
          </div>
        </div>
      </div>

      {/* Title and Description */}
      <div className="text-center space-y-2">
        <h3 className="text-xl font-semibold text-balance">{intro_data.title}</h3>
        <p className="text-sm text-muted-foreground leading-relaxed text-pretty">
          {intro_data.description}
        </p>
      </div>

      {/* Info Cards */}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Clock className="w-5 h-5 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{"预计时长"}</div>
            <div className="text-sm font-medium truncate">{intro_data.duration}</div>
          </div>
        </div>
        
        <div className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Target className="w-5 h-5 text-amber" />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{"特质数量"}</div>
            <div className="text-sm font-medium truncate">{intro_data.trait_count}{"个特质"}</div>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Gem className="w-5 h-5 text-amber" />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{"可用筹码"}</div>
            <div className="text-sm font-medium truncate">{intro_data.total_chips}{"个筹码"}</div>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-2xl bg-secondary/60 p-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-background">
            <Gift className="w-5 h-5 text-gold" />
          </div>
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{"完成奖励"}</div>
            <div className="text-sm font-medium truncate">{intro_data.reward}</div>
          </div>
        </div>
      </div>

      {/* Rules explanation */}
      <div className={cn(
        'mt-4 px-4 py-3 rounded-2xl border',
        'bg-amber-soft/50 border-amber/20'
      )}>
        <p className="text-sm text-muted-foreground leading-relaxed text-center">
          {"你有10个筹码，用来竞拍你最看重的特质。"}
          <br />
          {"筹码不够，必须取舍——就像真实人生。"}
        </p>
      </div>

      {/* Start Button */}
      <button
        onClick={onStart}
        className={cn(
          'mt-5 w-full h-12 rounded-xl text-base font-medium',
          'bg-amber hover:bg-amber/90 text-white',
          'flex items-center justify-center gap-1 group',
          'transition-all duration-200 active:scale-[0.98] touch-target'
        )}
      >
        <span>{"开始拍卖"}</span>
        <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
      </button>
    </div>
  )
}
