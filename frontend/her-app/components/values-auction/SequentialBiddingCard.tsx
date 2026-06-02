/**
 * 价值观拍卖会逐个展示模式卡片
 *
 * v4.0 沉浸式体验版：
 * - 卡片翻转入场动画
 * - 选择时粒子爆发效果
 * - 进度里程碑庆祝
 * - 触觉反馈
 * - 名额紧张时脉冲提示
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react'
import { Check, X, AlertTriangle, Lightbulb, ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionLotsCard, ValuesLot } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionLotsCard
  onSubmit: (bids: Array<{ lot_id: string; chips: number }>) => void
  isDualMode?: boolean
}

// 保留/放弃的选择记录
type ChoiceRecord = {
  lot_id: string
  choice: 'keep' | 'discard'
  timestamp: number
}

// Simple haptic feedback hook
function useHapticFeedback() {
  return useCallback((type: 'light' | 'medium' | 'heavy' | 'success' | 'error') => {
    if (!navigator.vibrate) return
    
    switch (type) {
      case 'light':
        navigator.vibrate(10)
        break
      case 'medium':
        navigator.vibrate(25)
        break
      case 'heavy':
        navigator.vibrate(50)
        break
      case 'success':
        navigator.vibrate([10, 50, 30])
        break
      case 'error':
        navigator.vibrate([50, 30, 50])
        break
    }
  }, [])
}

// Animated particle burst
function ParticleBurst({ trigger, color = 'var(--amber)' }: { trigger: boolean; color?: string }) {
  const [particles, setParticles] = useState<{ id: number; angle: number; speed: number }[]>([])
  
  useEffect(() => {
    if (trigger) {
      const newParticles = Array.from({ length: 12 }, (_, i) => ({
        id: i,
        angle: (360 / 12) * i + Math.random() * 30,
        speed: 40 + Math.random() * 40,
      }))
      setParticles(newParticles)
      const timer = setTimeout(() => setParticles([]), 600)
      return () => clearTimeout(timer)
    }
  }, [trigger])
  
  if (particles.length === 0) return null
  
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {particles.map((p) => {
        const rad = (p.angle * Math.PI) / 180
        const endX = 50 + Math.cos(rad) * p.speed
        const endY = 50 + Math.sin(rad) * p.speed
        
        return (
          <div
            key={p.id}
            className="absolute w-2 h-2 rounded-full animate-particle-burst"
            style={{
              left: '50%',
              top: '50%',
              backgroundColor: color,
              transform: 'translate(-50%, -50%)',
            }}
          />
        )
      })}
    </div>
  )
}

// Animated number counter
function AnimatedNumber({ value, duration = 500 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0)
  
  useEffect(() => {
    const start = display
    const diff = value - start
    const startTime = Date.now()
    
    const animate = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      
      setDisplay(Math.round(start + diff * eased))
      
      if (progress < 1) {
        requestAnimationFrame(animate)
      }
    }
    
    requestAnimationFrame(animate)
  }, [value, duration])
  
  return <span className="tabular-nums">{display}</span>
}

export function SequentialBiddingCard({ card, onSubmit, isDualMode }: Props) {
  const { lots_data } = card
  const { lots } = lots_data

  const [currentIndex, setCurrentIndex] = useState(0)
  const [choices, setChoices] = useState<ChoiceRecord[]>([])
  const [isChoicesExpanded, setIsChoicesExpanded] = useState(false)
  const [isAnimatingOut, setIsAnimatingOut] = useState(false)
  const [showParticles, setShowParticles] = useState(false)
  const [celebrationText, setCelebrationText] = useState('')
  const haptic = useHapticFeedback()

  const MAX_KEEP = 3

  const keptLots = useMemo(() =>
    choices.filter(c => c.choice === 'keep').map(c => c.lot_id),
    [choices]
  )

  const discardedLots = useMemo(() =>
    choices.filter(c => c.choice === 'discard').map(c => c.lot_id),
    [choices]
  )

  const remainingSlots = MAX_KEEP - keptLots.length
  const remainingLots = lots.length - currentIndex
  const currentLot = lots[currentIndex]
  const isSlotsFull = keptLots.length >= MAX_KEEP

  const phase = useMemo(() => {
    if (currentIndex < 3) return 'relaxed'
    if (currentIndex < 6) return 'tense'
    return 'critical'
  }, [currentIndex])

  const tensionHint = useMemo(() => {
    if (isSlotsFull) {
      return { text: '名额已满，需要替换才能保留', type: 'warning' as const }
    }
    if (phase === 'relaxed') {
      return { text: `已保留 ${keptLots.length}/${MAX_KEEP}，还能保留 ${remainingSlots} 件`, type: 'info' as const }
    }
    if (phase === 'tense') {
      return { text: `名额紧张！还能保留 ${remainingSlots} 件，剩余 ${remainingLots} 件待选`, type: 'tense' as const }
    }
    return { text: `最后阶段！还能保留 ${remainingSlots} 件`, type: 'critical' as const }
  }, [keptLots.length, remainingSlots, remainingLots, phase, isSlotsFull])

  const conflictHint = currentLot?.conflict_hint || ''

  // Milestone celebration
  const checkMilestone = useCallback((newKeptCount: number, newTotalChoices: number) => {
    if (newKeptCount === 1) {
      setCelebrationText('首选珍品!')
      setTimeout(() => setCelebrationText(''), 1500)
    } else if (newKeptCount === MAX_KEEP) {
      setCelebrationText('名额已满!')
      setTimeout(() => setCelebrationText(''), 1500)
    } else if (newTotalChoices === Math.floor(lots.length / 2)) {
      setCelebrationText('半程完成!')
      setTimeout(() => setCelebrationText(''), 1500)
    }
  }, [lots.length])

  const handleKeep = () => {
    if (!currentLot || isSlotsFull) {
      if (isSlotsFull) haptic('error')
      return
    }

    setShowParticles(true)
    haptic('success')

    const newChoices = [...choices, {
      lot_id: currentLot.lot_id,
      choice: 'keep' as const,
      timestamp: Date.now()
    }]
    setChoices(newChoices)

    checkMilestone(keptLots.length + 1, newChoices.length)
    
    setTimeout(() => {
      setShowParticles(false)
      moveToNext()
    }, 400)
  }

  const handleDiscard = () => {
    if (!currentLot) return

    haptic('light')

    const newChoices = [...choices, {
      lot_id: currentLot.lot_id,
      choice: 'discard' as const,
      timestamp: Date.now()
    }]
    setChoices(newChoices)

    checkMilestone(keptLots.length, newChoices.length)
    moveToNext()
  }

  const moveToNext = () => {
    setIsAnimatingOut(true)
    
    setTimeout(() => {
      if (currentIndex < lots.length - 1) {
        setCurrentIndex(prev => prev + 1)
      } else {
        handleSubmit()
      }
      setIsAnimatingOut(false)
    }, 250)
  }

  const handleSubmit = () => {
    const bids = lots.map(lot => ({
      lot_id: lot.lot_id,
      chips: keptLots.includes(lot.lot_id) ? 3 : 0
    }))
    onSubmit(bids)
  }

  const handleReplace = (targetLotId: string) => {
    setChoices(prev => prev.filter(c => c.lot_id !== targetLotId))

    setShowParticles(true)
    haptic('success')

    setChoices(prev => [...prev, {
      lot_id: currentLot.lot_id,
      choice: 'keep',
      timestamp: Date.now()
    }])

    setTimeout(() => {
      setShowParticles(false)
      moveToNext()
    }, 400)
  }

  // Completion screen with celebration
  if (currentIndex >= lots.length) {
    return (
      <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in relative overflow-hidden">
        {/* Celebration background glow */}
        <div className="absolute inset-0 bg-gradient-to-br from-amber/10 to-gold-soft/20 animate-ambient-pulse" />
        
        <div className="relative z-10">
          <div className="flex items-center justify-center gap-2 mb-4">
            <Sparkles className="w-5 h-5 text-amber animate-pulse-soft" />
            <h3 className="text-xl font-bold text-center">{"取舍完成"}</h3>
            <Sparkles className="w-5 h-5 text-amber animate-pulse-soft" />
          </div>

          <div className="rounded-2xl bg-secondary/60 p-4 mb-4">
            <div className="text-sm text-muted-foreground mb-3">{"你保留了："}</div>
            {keptLots.map((lotId, index) => {
              const lot = lots.find(l => l.lot_id === lotId)
              return (
                <div 
                  key={lotId} 
                  className="flex items-center gap-3 text-foreground font-medium py-2 animate-slide-in-right"
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  <div className="w-8 h-8 rounded-full bg-amber-soft flex items-center justify-center text-lg">
                    {lot?.icon}
                  </div>
                  <span>{lot?.title}</span>
                  <Check className="w-4 h-4 text-amber ml-auto" />
                </div>
              )
            })}
            {keptLots.length === 0 && (
              <div className="text-muted-foreground text-sm py-2">{"没有保留任何拍品"}</div>
            )}
          </div>

          <button
            onClick={handleSubmit}
            className={cn(
              'w-full h-14 rounded-xl text-base font-semibold',
              'bg-gradient-to-r from-amber to-gold text-white',
              'transition-all duration-200 active:scale-[0.98] touch-target',
              'shadow-lg shadow-amber/20',
              'animate-elastic-pop'
            )}
          >
            {"封盘揭晓"}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={cn(
      'rounded-3xl border border-border bg-card p-6 shadow-sm will-change-transform relative overflow-hidden',
      isAnimatingOut ? 'animate-slide-scale-out' : 'animate-slide-scale-in'
    )}>
      {/* Celebration overlay */}
      {celebrationText && (
        <div className="absolute inset-0 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-amber text-white px-6 py-3 rounded-2xl font-bold text-lg animate-dimension-complete shadow-xl">
            {celebrationText}
          </div>
        </div>
      )}

      {/* Progress indicator */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
          <span className="font-medium">
            {"第 "}<AnimatedNumber value={currentIndex + 1} />{" 件"}
          </span>
          <span>{"共 "}{lots.length}{" 件"}</span>
        </div>
        <div className="h-2 bg-secondary rounded-full overflow-hidden">
          <div 
            className={cn(
              'h-full bg-gradient-to-r from-amber to-gold rounded-full transition-all duration-500',
              phase === 'critical' && 'animate-progress-glow'
            )}
            style={{ width: `${((currentIndex + 1) / lots.length) * 100}%` }}
          />
        </div>
        {/* Dot indicators */}
        <div className="flex justify-center gap-1.5 mt-3">
          {lots.map((lot, i) => {
            const choice = choices.find(c => c.lot_id === lot.lot_id)
            const isCurrent = i === currentIndex
            const isKept = choice?.choice === 'keep'
            const isDiscarded = choice?.choice === 'discard'
            
            return (
              <div
                key={lot.lot_id}
                className={cn(
                  'rounded-full transition-all duration-300',
                  isCurrent && 'w-6 h-2 bg-amber animate-pulse',
                  !isCurrent && isKept && 'w-2 h-2 bg-amber',
                  !isCurrent && isDiscarded && 'w-2 h-2 bg-secondary',
                  !isCurrent && !choice && 'w-2 h-2 bg-border'
                )}
              />
            )
          })}
        </div>
      </div>

      {/* Dual mode hint */}
      {isDualMode && (
        <div className="rounded-xl px-3 py-2 mb-4 border bg-amber-soft/50 border-amber/20">
          <p className="text-xs text-muted-foreground text-center">
            {"秘密取舍，封盘前没人知道你选了什么"}
          </p>
        </div>
      )}

      {/* Tension hint */}
      <div className={cn(
        'rounded-xl px-4 py-3 mb-4 border transition-all duration-300',
        tensionHint.type === 'critical' && 'bg-destructive/10 border-destructive/30 animate-pulse-soft',
        tensionHint.type === 'tense' && 'bg-amber-soft/60 border-amber/30',
        tensionHint.type === 'warning' && 'bg-amber-soft/60 border-amber/30',
        tensionHint.type === 'info' && 'bg-secondary/60 border-border'
      )}>
        <p className={cn(
          'text-sm text-center font-medium flex items-center justify-center gap-2',
          tensionHint.type === 'critical' && 'text-destructive',
          tensionHint.type === 'tense' && 'text-amber',
          tensionHint.type === 'warning' && 'text-amber',
          tensionHint.type === 'info' && 'text-muted-foreground'
        )}>
          {tensionHint.type !== 'info' && <AlertTriangle className="w-4 h-4" />}
          {tensionHint.text}
        </p>
      </div>

      {/* Current lot card with flip animation */}
      <div
        className={cn(
          'relative rounded-2xl p-5 border-2 mb-4 transition-all duration-300',
          'bg-gradient-to-br from-amber-soft/40 to-gold-soft/40',
          showParticles && 'animate-elastic-pop'
        )}
        style={{ borderColor: currentLot?.theme_color || 'var(--amber)' }}
      >
        {/* Particle burst on selection */}
        <ParticleBurst trigger={showParticles} color="var(--amber)" />
        
        {/* Lot icon with entrance animation */}
        <div className="text-center mb-4">
          <div className={cn(
            'inline-flex items-center justify-center w-20 h-20 rounded-2xl',
            'bg-gradient-to-br from-amber/10 to-gold/10',
            'text-5xl animate-scale-in'
          )}>
            {currentLot?.icon || '?'}
          </div>
        </div>

        {/* Lot title */}
        <div className="text-center mb-4">
          <h4 className="text-xl font-bold text-foreground mb-2 text-balance animate-fade-in">
            {currentLot?.title}
          </h4>
          <p className="text-sm text-muted-foreground italic leading-relaxed text-pretty animate-fade-in" style={{ animationDelay: '100ms' }}>
            {`"${currentLot?.interpretation}"`}
          </p>
        </div>

        {/* Conflict hint */}
        {conflictHint && phase !== 'relaxed' && (
          <div className="rounded-xl px-3 py-2 border bg-gold-soft/50 border-gold/20 animate-fade-in" style={{ animationDelay: '200ms' }}>
            <p className="text-xs text-muted-foreground text-center flex items-center justify-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5 text-gold" />
              {conflictHint}
            </p>
          </div>
        )}

        {/* Replace panel when full */}
        {isSlotsFull && (
          <div className="mt-4 rounded-xl p-4 border bg-destructive/5 border-destructive/20 animate-fade-in">
            <p className="text-xs text-muted-foreground text-center mb-3 font-medium">
              {"名额已满，保留此项需要替换："}
            </p>
            <div className="flex flex-col gap-2">
              {keptLots.map(lotId => {
                const lot = lots.find(l => l.lot_id === lotId)
                return (
                  <button
                    key={lotId}
                    onClick={() => handleReplace(lotId)}
                    className={cn(
                      'px-4 py-3 rounded-xl text-sm font-medium',
                      'bg-background border border-border',
                      'hover:bg-amber-soft hover:border-amber/30',
                      'transition-all touch-target active:scale-[0.98]',
                      'flex items-center gap-2'
                    )}
                  >
                    <span className="text-lg">{lot?.icon}</span>
                    <span>{"替换："}{lot?.title}</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleDiscard}
          className={cn(
            'flex-1 h-14 rounded-xl text-base font-semibold',
            'bg-secondary text-muted-foreground',
            'flex items-center justify-center gap-2',
            'hover:bg-secondary/80 active:scale-[0.98]',
            'transition-all touch-target'
          )}
        >
          <X className="w-5 h-5" />
          {"放弃"}
        </button>
        <button
          onClick={handleKeep}
          disabled={isSlotsFull}
          className={cn(
            'flex-1 h-14 rounded-xl text-base font-semibold',
            'flex items-center justify-center gap-2',
            'transition-all touch-target',
            isSlotsFull
              ? 'bg-secondary text-muted-foreground cursor-not-allowed opacity-60'
              : 'bg-gradient-to-r from-amber to-gold text-white shadow-lg shadow-amber/20 active:scale-[0.98]'
          )}
        >
          <Check className="w-5 h-5" />
          {isSlotsFull ? '名额已满' : '保留'}
        </button>
      </div>

      {/* Choices summary */}
      {choices.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <button
            onClick={() => setIsChoicesExpanded(!isChoicesExpanded)}
            className="w-full flex items-center justify-between text-xs text-muted-foreground mb-2 touch-target"
          >
            <span className="font-medium">{"已选择 "}<AnimatedNumber value={choices.length} />{" 件"}</span>
            {isChoicesExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
          
          {isChoicesExpanded && (
            <div className="flex gap-4 animate-fade-in">
              <div className="flex-1">
                <div className="text-xs text-amber mb-2 font-medium">
                  {"保留（"}{keptLots.length}{"/"}{MAX_KEEP}{"）"}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {keptLots.map(lotId => {
                    const lot = lots.find(l => l.lot_id === lotId)
                    return (
                      <div 
                        key={lotId} 
                        className="px-2.5 py-1.5 bg-amber-soft rounded-lg text-xs text-foreground font-medium flex items-center gap-1"
                      >
                        {lot?.icon} {lot?.title?.substring(0, 6)}
                      </div>
                    )
                  })}
                  {keptLots.length === 0 && (
                    <span className="text-xs text-muted-foreground">{"暂无"}</span>
                  )}
                </div>
              </div>
              <div className="flex-1">
                <div className="text-xs text-muted-foreground mb-2">
                  {"放弃（"}{discardedLots.length}{"）"}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {discardedLots.slice(-3).map(lotId => {
                    const lot = lots.find(l => l.lot_id === lotId)
                    return (
                      <div 
                        key={lotId} 
                        className="px-2.5 py-1.5 bg-secondary rounded-lg text-xs text-muted-foreground"
                      >
                        {lot?.title?.substring(0, 6)}
                      </div>
                    )
                  })}
                  {discardedLots.length > 3 && (
                    <span className="text-xs text-muted-foreground">+{discardedLots.length - 3}</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
