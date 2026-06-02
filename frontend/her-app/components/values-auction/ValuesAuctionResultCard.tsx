/**
 * 价值观拍卖会结果卡片
 *
 * v2.0 更新：
 * - 先展示"你拍下了什么人生"
 * - 再展示隐藏价值分析
 * - 最后展示价值倾向标签
 * - Top3 翻牌揭晓动效
 */

import React, { useState, useEffect, useCallback } from 'react'
import { Share2, Eye, ArrowRight, Check, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionResultCard } from '@/lib/api/endpoints/valuesAuction'
import { HIDDEN_VALUE_LABELS } from '@/lib/api/endpoints/valuesAuction'

// Haptic feedback helper
function useHapticFeedback() {
  return useCallback((type: 'light' | 'medium' | 'heavy' | 'success' | 'error') => {
    if (!navigator.vibrate) return
    
    switch (type) {
      case 'light': navigator.vibrate(10); break
      case 'medium': navigator.vibrate(25); break
      case 'heavy': navigator.vibrate(50); break
      case 'success': navigator.vibrate([10, 50, 30]); break
      case 'error': navigator.vibrate([50, 30, 50]); break
    }
  }, [])
}

type Props = {
  card: ValuesAuctionResultCard
  onViewInterpretation?: () => void
  onShare?: () => void
  onContinue?: () => void
}

export function ValuesAuctionResultCardComponent({ card, onViewInterpretation, onShare, onContinue }: Props) {
  const { result_data } = card
  const { hidden_values, top_hidden_values, value_type, value_labels, top3, abandoned, reward } = result_data
  const haptic = useHapticFeedback()

  // 翻牌动效状态
  const [revealedCount, setRevealedCount] = useState(0)
  const [isAutoRevealing, setIsAutoRevealing] = useState(true)
  const [showConfetti, setShowConfetti] = useState(false)
  const [isRevealed, setIsRevealed] = useState(false)
  
  // 初始入场动画
  useEffect(() => {
    const timer = setTimeout(() => setIsRevealed(true), 100)
    return () => clearTimeout(timer)
  }, [])

  // 自动翻牌
  useEffect(() => {
    if (!isAutoRevealing) return
    if (revealedCount < 3 && revealedCount < top3.length) {
      const timer = setTimeout(() => {
        setRevealedCount(prev => prev + 1)
        haptic('medium')
        
        // 最后一张牌翻完时显示庆祝
        if (revealedCount === Math.min(2, top3.length - 1)) {
          setTimeout(() => {
            setShowConfetti(true)
            haptic('success')
          }, 300)
        }
      }, 600)
      return () => clearTimeout(timer)
    }
  }, [revealedCount, isAutoRevealing, top3.length, haptic])

  // 手动点击翻牌
  const handleRevealClick = () => {
    if (revealedCount < top3.length) {
      setIsAutoRevealing(false)
      setRevealedCount(prev => prev + 1)
      haptic('medium')
      
      // 最后一张牌翻完时显示庆祝
      if (revealedCount === Math.min(2, top3.length - 1)) {
        setTimeout(() => {
          setShowConfetti(true)
          haptic('success')
        }, 300)
      }
    }
  }

  // 根据价值观类型选择颜色
  const typeColor = getTypeColor(value_type)

  // 构建隐藏价值解读
  const hiddenValueSummary = top_hidden_values && top_hidden_values.length > 0
    ? `底层真正强势的是：${top_hidden_values.map(hv => HIDDEN_VALUE_LABELS[hv.key] || hv.key).join('、')}`
    : ''

  return (
    <>
      {/* 简单的庆祝效果 */}
      {showConfetti && (
        <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden">
          {Array.from({ length: 30 }).map((_, i) => (
            <div
              key={i}
              className="absolute w-3 h-3 animate-confetti-fall"
              style={{
                left: `${Math.random() * 100}%`,
                top: '-20px',
                backgroundColor: ['var(--amber)', 'var(--gold)', 'var(--rose)', 'var(--lavender)'][Math.floor(Math.random() * 4)],
                borderRadius: Math.random() > 0.5 ? '50%' : '2px',
                animationDelay: `${Math.random() * 500}ms`,
                animationDuration: `${2000 + Math.random() * 1000}ms`,
                transform: `rotate(${Math.random() * 360}deg)`,
              }}
            />
          ))}
        </div>
      )}
      
      <div className={cn(
        'rounded-3xl border border-border bg-card p-6 shadow-sm max-h-[80vh] overflow-y-auto scroll-fade-bottom',
        isRevealed ? 'animate-score-reveal' : 'opacity-0 scale-90'
      )}>
        {/* 标题 */}
        <div className="text-center mb-6">
          <div className="relative flex justify-center mb-3">
            <div className="relative will-change-transform">
              <div className="absolute inset-0 rounded-full animate-ping-slow will-change-transform bg-amber/15" />
              <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-amber-soft to-gold-soft">
                <Trophy className="w-7 h-7 text-amber animate-heartbeat" />
              </div>
            </div>
          </div>
          <h2 className="text-xl font-semibold animate-fade-in" style={{ animationDelay: '200ms' }}>{"拍卖完成！"}</h2>
        </div>

        {/* 你拍下了什么人生 */}
        <div className="mb-5 rounded-2xl bg-secondary/40 p-4 border border-border">
          <h3 className="text-sm font-medium text-muted-foreground mb-3">{"你拍下了这些人生"}</h3>
          <div className="space-y-2.5">
            {top3.slice(0, revealedCount).map((lot, i) => (
              <div
                key={lot.lot_id}
                className={cn(
                  'rounded-xl p-3 border will-change-transform perspective-1000',
                  'bg-amber-soft/50 border-amber/20',
                  'animate-card-flip-in'
                )}
                style={{ animationDelay: `${i * 100}ms` }}
              >
                <div className="flex items-center gap-3">
                  {/* 排名 */}
                  <div className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center font-semibold text-sm',
                    i === 0 && 'bg-amber text-white',
                    i === 1 && 'bg-amber/60 text-white',
                    i === 2 && 'bg-amber/30 text-foreground'
                  )}>
                    {i + 1}
                  </div>
                  {/* 拍品信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-foreground text-sm truncate">{lot.title}</div>
                    {lot.interpretation && (
                      <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{lot.interpretation}</div>
                    )}
                  </div>
                  {/* 筹码数 */}
                  <div className="text-xl font-bold text-amber tabular-nums">
                    {lot.chips}
                  </div>
                </div>
              </div>
            ))}
            
            {/* 正在揭晓的拍品 - 支持点击翻牌 */}
            {revealedCount < top3.length && top3[revealedCount] && (
              <button
                onClick={handleRevealClick}
                className={cn(
                  'w-full rounded-xl p-3 border transition-all touch-target',
                  'bg-secondary border-border',
                  isAutoRevealing ? 'animate-pulse' : 'hover:bg-secondary/80 active:scale-[0.98]'
                )}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center font-semibold text-sm bg-muted text-muted-foreground">
                    {revealedCount + 1}
                  </div>
                  <div className="flex-1 text-muted-foreground text-sm text-left">
                    {isAutoRevealing ? '正在揭晓...' : '点击翻开'}
                  </div>
                </div>
              </button>
            )}
          </div>
        </div>

        {/* 隐藏价值分析 */}
        {hidden_values && top_hidden_values && top_hidden_values.length > 0 && (
          <div className="mb-5 rounded-2xl bg-purple-soft/50 p-4 border border-purple/20 animate-fade-in">
            <h4 className="text-sm font-medium text-purple mb-3">{"底层价值分析"}</h4>
            <div className="space-y-2.5">
              {top_hidden_values.slice(0, 3).map(hv => (
                <div key={hv.key} className="flex items-center gap-2.5">
                  <div className="text-sm text-foreground min-w-[80px]">
                    {HIDDEN_VALUE_LABELS[hv.key] || hv.key}
                  </div>
                  <div className="flex-1">
                    <div className="h-2 bg-purple/10 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-purple rounded-full transition-all duration-500"
                        style={{ width: `${hv.weight * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-sm text-purple font-medium tabular-nums min-w-[40px] text-right">
                    {Math.round(hv.weight * 100)}%
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3">
              {hiddenValueSummary}
            </p>
          </div>
        )}

        {/* 价值观类型标签 */}
        <div className={cn(
          'text-center mb-4 p-4 rounded-2xl animate-fade-in',
          typeColor.bg
        )}>
          <div className={cn('text-sm font-semibold mb-2', typeColor.text)}>{value_type}</div>
          <div className="flex flex-wrap justify-center gap-1.5">
            {value_labels.map((label, i) => (
              <span 
                key={i} 
                className={cn(
                  'px-2.5 py-1 rounded-full text-xs font-medium',
                  typeColor.tagBg, typeColor.tagText
                )}
              >
                {label}
              </span>
            ))}
          </div>
        </div>

        {/* 放弃的拍品 */}
        {abandoned.length > 0 && (
          <div className="mb-4 rounded-xl bg-secondary/40 p-3 animate-fade-in">
            <h4 className="text-xs text-muted-foreground mb-1.5">{"你主动放弃了"}</h4>
            <div className="text-xs text-muted-foreground/80 leading-relaxed">
              {abandoned.slice(0, 5).join('、')}
              {abandoned.length > 5 && ` 等${abandoned.length}项`}
            </div>
          </div>
        )}

        {/* 奖励提示 */}
        {reward && (
          <div className="rounded-xl bg-sage-soft/50 border border-sage/20 p-3 mb-4 text-center animate-fade-in">
            <span className="text-sage text-sm flex items-center justify-center gap-1.5">
              <Check className="w-4 h-4" />
              {reward}
            </span>
          </div>
        )}

      {/* 操作按钮 - 垂直堆叠布局 */}
        <div className="flex flex-col gap-2.5">
          {onViewInterpretation && (
            <button
              onClick={onViewInterpretation}
              className={cn(
                'w-full h-12 rounded-xl text-base font-medium',
                'bg-amber hover:bg-amber/90 text-white',
                'flex items-center justify-center gap-2 group',
                'transition-all touch-target active:scale-[0.98]'
              )}
            >
              <Eye className="w-4 h-4" />
              {"查看AI解读"}
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </button>
          )}
          
          <div className="flex gap-2.5">
            {onShare && (
              <button
                onClick={onShare}
                className={cn(
                  'flex-1 h-11 rounded-xl text-sm font-medium',
                  'bg-secondary text-foreground',
                  'flex items-center justify-center gap-1.5',
                  'hover:bg-secondary/80 transition-all touch-target active:scale-[0.98]'
                )}
              >
                <Share2 className="w-4 h-4" />
                {"分享"}
              </button>
            )}
            {onContinue && (
              <button
                onClick={onContinue}
                className={cn(
                  'flex-1 h-11 rounded-xl text-sm font-medium',
                  'bg-secondary text-muted-foreground',
                  'flex items-center justify-center',
                  'hover:bg-secondary/80 transition-all touch-target active:scale-[0.98]'
                )}
              >
                {"继续"}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

// ============================================================
// 辅助函数
// ============================================================

function getTypeColor(valueType: string) {
  if (valueType.includes('安全感') || valueType.includes('安全')) {
    return { bg: 'bg-sage-soft/60', text: 'text-sage', tagBg: 'bg-sage/10', tagText: 'text-sage' }
  } else if (valueType.includes('自由')) {
    return { bg: 'bg-sage-soft/60', text: 'text-sage', tagBg: 'bg-sage/10', tagText: 'text-sage' }
  } else if (valueType.includes('情感') || valueType.includes('连接')) {
    return { bg: 'bg-rose-soft/60', text: 'text-rose', tagBg: 'bg-rose/10', tagText: 'text-rose' }
  } else if (valueType.includes('成就') || valueType.includes('物质')) {
    return { bg: 'bg-gold-soft/60', text: 'text-gold', tagBg: 'bg-gold/10', tagText: 'text-gold' }
  } else if (valueType.includes('利他') || valueType.includes('奉献')) {
    return { bg: 'bg-lavender-soft/60', text: 'text-lavender', tagBg: 'bg-lavender/10', tagText: 'text-lavender' }
  } else if (valueType.includes('意义') || valueType.includes('平静')) {
    return { bg: 'bg-lavender-soft/60', text: 'text-lavender', tagBg: 'bg-lavender/10', tagText: 'text-lavender' }
  } else {
    return { bg: 'bg-amber-soft/60', text: 'text-amber', tagBg: 'bg-amber/10', tagText: 'text-amber' }
  }
}
