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
import { Share2, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionResultCard } from '@/lib/api/endpoints/valuesAuction'
import { HIDDEN_VALUE_LABELS, HIGHER_ORDER_LABELS } from '@/lib/api/endpoints/valuesAuction'

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
  const { top_hidden_values, top3, higher_order_summary, internal_tensions } = result_data
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
        <div className="mb-4 rounded-2xl bg-amber-soft/30 p-3 border border-amber/20">
          <h3 className="text-xs font-medium text-muted-foreground mb-2">{"拍卖结果"}</h3>
          <div className="space-y-2">
            {top3.slice(0, revealedCount).map((lot, i) => (
              <div
                key={lot.lot_id}
                className={cn(
                  'rounded-xl p-2.5 border will-change-transform perspective-1000',
                  'bg-card border-border',
                  'animate-card-flip-in'
                )}
                style={{ animationDelay: `${i * 100}ms` }}
              >
                <div className="flex items-center gap-2.5">
                  {/* 排名 */}
                  <div className={cn(
                    'w-7 h-7 rounded-full flex items-center justify-center font-semibold text-xs',
                    i === 0 && 'bg-amber text-white',
                    i === 1 && 'bg-amber/60 text-white',
                    i === 2 && 'bg-amber/30 text-foreground'
                  )}>
                    {i + 1}
                  </div>
                  {/* 拍品标题 */}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-foreground text-sm truncate">{lot.title}</div>
                  </div>
                  {/* 筹码数 */}
                  <div className="text-lg font-bold text-amber tabular-nums">
                    {lot.chips}筹码
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

        {/* 底层价值 - 简化为标签 */}
        {top_hidden_values && top_hidden_values.length > 0 && (
          <div className="mb-3 flex items-center gap-2 animate-fade-in">
            <span className="text-xs text-muted-foreground">{"核心价值："}</span>
            <div className="flex gap-1.5">
              {top_hidden_values.slice(0, 3).map(hv => (
                <span key={hv.key} className="px-2 py-1 bg-purple-soft/50 rounded-md text-xs text-purple font-medium">
                  {HIDDEN_VALUE_LABELS[hv.key] || hv.key}
                </span>
              ))}
            </div>
          </div>
        )}

        {higher_order_summary && higher_order_summary.length > 0 && (
          <div className="mb-3 rounded-2xl bg-sage-soft/25 p-3 border border-sage/20">
            <div className="text-xs text-muted-foreground mb-2">价值方向</div>
            <div className="flex flex-wrap gap-2">
              {higher_order_summary.slice(0, 2).map(item => (
                <span key={item.key} className="px-2 py-1 rounded-md bg-white text-xs text-sage font-medium border border-sage/20">
                  {(item.label || HIGHER_ORDER_LABELS[item.key] || item.key)} {Math.round(item.weight * 100)}%
                </span>
              ))}
            </div>
          </div>
        )}

        {internal_tensions && internal_tensions.length > 0 && (
          <div className="mb-4 rounded-2xl bg-rose-soft/20 p-3 border border-rose/20">
            <div className="text-xs text-muted-foreground mb-1">你内部的拉扯</div>
            <div className="text-sm text-foreground leading-relaxed">
              {internal_tensions[0].description || `${internal_tensions[0].left_label || internal_tensions[0].left} 和 ${internal_tensions[0].right_label || internal_tensions[0].right} 同时都不低`}
            </div>
          </div>
        )}

      <div className="flex justify-center gap-3">
        {onViewInterpretation && (
          <button
            onClick={onViewInterpretation}
            className={cn(
              'px-4 py-2 rounded-full text-sm transition-all touch-target active:scale-95',
              'bg-lavender/10 text-lavender hover:bg-lavender/20'
            )}
          >
            {"查看AI解读"}
          </button>
        )}
        {onShare && (
          <div className="flex justify-center">
            <button
              onClick={onShare}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all touch-target active:scale-95',
                'bg-amber/10 text-amber hover:bg-amber/20'
              )}
            >
              <Share2 className="w-4 h-4" />
              {"分享结果"}
            </button>
          </div>
        )}
      </div>
      </div>
    </>
  )
}

// ============================================================
// 导出
// ============================================================
