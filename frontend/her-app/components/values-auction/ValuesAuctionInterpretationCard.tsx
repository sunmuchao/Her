/**
 * 价值观拍卖会AI解读卡片
 */

import React, { useState } from 'react'
import { Bot, Heart, BarChart3, Lightbulb, AlertTriangle, ArrowRight, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionInterpretationCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionInterpretationCard
  onContinue?: () => void
}

// 可折叠的分析区块组件
function CollapsibleSection({
  title,
  icon: Icon,
  iconColor,
  bgColor,
  borderColor,
  children,
  defaultExpanded = true
}: {
  title: string
  icon: React.ElementType
  iconColor: string
  bgColor: string
  borderColor: string
  children: React.ReactNode
  defaultExpanded?: boolean
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  
  return (
    <div className={cn('rounded-2xl border overflow-hidden transition-all', bgColor, borderColor)}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between touch-target"
      >
        <div className="flex items-center gap-2">
          <Icon className={cn('w-4 h-4', iconColor)} />
          <span className="font-medium text-sm text-foreground">{title}</span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted-foreground" />
        )}
      </button>
      {isExpanded && (
        <div className="px-4 pb-4 animate-fade-in">
          {children}
        </div>
      )}
    </div>
  )
}

export function ValuesAuctionInterpretationCardComponent({ card, onContinue }: Props) {
  const { interpretation_data } = card
  const { summary, love_style, match_suggestions, caution_traits, top3_analysis, higher_order_analysis } = interpretation_data

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in max-h-[80vh] overflow-y-auto scroll-fade-bottom">
      {/* 标题 */}
      <div className="text-center mb-5">
        <div className="relative flex justify-center mb-3">
          <div className="relative will-change-transform">
            <div className="absolute inset-0 rounded-full animate-ping-slow will-change-transform bg-lavender/15" />
            <div className="relative flex items-center justify-center w-14 h-14 rounded-full bg-gradient-to-br from-lavender-soft to-purple-soft">
              <Bot className="w-6 h-6 text-lavender" />
            </div>
          </div>
        </div>
        <h2 className="text-lg font-semibold">{"AI 价值观解读"}</h2>
      </div>

      <div className="space-y-3">
        {/* 概述 */}
        <CollapsibleSection
          title="价值观画像"
          icon={BarChart3}
          iconColor="text-lavender"
          bgColor="bg-lavender-soft/30"
          borderColor="border-lavender/20"
          defaultExpanded={true}
        >
          <p className="text-sm text-muted-foreground leading-relaxed">{summary}</p>
        </CollapsibleSection>

        {/* 恋爱风格 */}
        <CollapsibleSection
          title="恋爱风格"
          icon={Heart}
          iconColor="text-rose"
          bgColor="bg-rose-soft/30"
          borderColor="border-rose/20"
          defaultExpanded={true}
        >
          <p className="text-sm text-muted-foreground leading-relaxed">{love_style}</p>
        </CollapsibleSection>

        {/* Top3 分析 */}
        {top3_analysis && top3_analysis.length > 0 && (
          <CollapsibleSection
            title="TOP3 特质分析"
            icon={BarChart3}
            iconColor="text-amber"
            bgColor="bg-amber-soft/30"
            borderColor="border-amber/20"
            defaultExpanded={true}
          >
            <div className="space-y-2">
              {top3_analysis.map((trait, i) => (
                <div key={i} className="rounded-xl bg-background p-3 border border-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-sm text-foreground">{trait.title}</span>
                    <span className="text-amber font-semibold text-sm tabular-nums">{trait.chips}{"筹码"}</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{trait.interpretation}</p>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {higher_order_analysis && higher_order_analysis.length > 0 && (
          <CollapsibleSection
            title="价值方向"
            icon={ArrowRight}
            iconColor="text-sky"
            bgColor="bg-sky-50"
            borderColor="border-sky-200"
            defaultExpanded={false}
          >
            <div className="space-y-2">
              {higher_order_analysis.slice(0, 2).map((item, i) => (
                <div key={i} className="rounded-xl bg-background p-3 border border-border">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm text-foreground">{item.label || item.key}</span>
                    <span className="text-sky-600 font-semibold text-sm">{Math.round(item.weight * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {/* 匹配建议 */}
        {match_suggestions && match_suggestions.length > 0 && (
          <CollapsibleSection
            title="匹配建议"
            icon={Lightbulb}
            iconColor="text-sage"
            bgColor="bg-sage-soft/30"
            borderColor="border-sage/20"
            defaultExpanded={false}
          >
            <div className="space-y-2">
              {match_suggestions.map((suggestion, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="text-sage mt-0.5">{"•"}</span>
                  <span className="leading-relaxed">{suggestion}</span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {/* 注意事项 */}
        {caution_traits && caution_traits.length > 0 && (
          <CollapsibleSection
            title="需要注意"
            icon={AlertTriangle}
            iconColor="text-gold"
            bgColor="bg-gold-soft/30"
            borderColor="border-gold/20"
            defaultExpanded={false}
          >
            <div className="space-y-2">
              {caution_traits.map((caution, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="text-gold mt-0.5">{"•"}</span>
                  <span className="leading-relaxed">{caution}</span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>

      {/* 继续按钮 */}
      {onContinue && (
        <button
          onClick={onContinue}
          className={cn(
            'w-full h-12 mt-5 rounded-xl text-base font-medium',
            'bg-lavender hover:bg-lavender/90 text-white',
            'flex items-center justify-center gap-2 group',
            'transition-all touch-target active:scale-[0.98]'
          )}
        >
          {"继续聊天"}
          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
        </button>
      )}
    </div>
  )
}
