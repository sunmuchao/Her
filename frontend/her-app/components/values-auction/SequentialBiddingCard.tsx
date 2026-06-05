/**
 * 价值观拍卖会逐个展示模式卡片
 *
 * v5.0 真实竞拍版：
 * - 每件拍品可投 0-3 筹码
 * - 过程里可撤码重分
 * - 完成后可做最终调仓，再封盘揭晓
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react'
import { Minus, Plus, ChevronDown, ChevronUp, Sparkles, AlertTriangle, Lightbulb } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ValuesAuctionLotsCard } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionLotsCard
  onSubmit: (bids: Array<{ lot_id: string; chips: number }>) => void
  isDualMode?: boolean
}

type ChoiceRecord = {
  lot_id: string
  chips: number
  timestamp: number
}

function useHapticFeedback() {
  return useCallback((type: 'light' | 'medium' | 'success' | 'error') => {
    if (!navigator.vibrate) return
    switch (type) {
      case 'light':
        navigator.vibrate(10)
        break
      case 'medium':
        navigator.vibrate(25)
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

function ParticleBurst({ trigger, color = 'var(--amber)' }: { trigger: boolean; color?: string }) {
  const [particles, setParticles] = useState<{ id: number }[]>([])

  useEffect(() => {
    if (!trigger) return
    setParticles(Array.from({ length: 12 }, (_, i) => ({ id: i })))
    const timer = setTimeout(() => setParticles([]), 600)
    return () => clearTimeout(timer)
  }, [trigger])

  if (particles.length === 0) return null

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {particles.map((p) => (
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
      ))}
    </div>
  )
}

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
      if (progress < 1) requestAnimationFrame(animate)
    }

    requestAnimationFrame(animate)
  }, [value, duration])

  return <span className="tabular-nums">{display}</span>
}

export function SequentialBiddingCard({ card, onSubmit, isDualMode }: Props) {
  const { lots_data } = card
  const { lots, total_chips, max_bid } = lots_data
  const perLotCap = Math.min(max_bid ?? 3, 3)

  const [currentIndex, setCurrentIndex] = useState(0)
  const [bids, setBids] = useState<Record<string, number>>(() =>
    Object.fromEntries(lots.map((lot) => [lot.lot_id, 0])),
  )
  const [choices, setChoices] = useState<ChoiceRecord[]>([])
  const [draftBid, setDraftBid] = useState(0)
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false)
  const [isAnimatingOut, setIsAnimatingOut] = useState(false)
  const [showParticles, setShowParticles] = useState(false)
  const [celebrationText, setCelebrationText] = useState('')
  const haptic = useHapticFeedback()

  const currentLot = lots[currentIndex]
  const currentLotId = currentLot?.lot_id || ''

  const totalUsed = useMemo(
    () => Object.values(bids).reduce((sum, chips) => sum + chips, 0),
    [bids],
  )
  const remainingChips = total_chips - totalUsed
  const revisableLots = useMemo(
    () => lots.filter((lot) => lot.lot_id !== currentLotId && (bids[lot.lot_id] || 0) > 0),
    [lots, currentLotId, bids],
  )
  const chosenLots = useMemo(
    () => lots
      .map((lot) => ({ ...lot, chips: bids[lot.lot_id] || 0 }))
      .filter((lot) => lot.chips > 0)
      .sort((a, b) => b.chips - a.chips),
    [lots, bids],
  )
  const completedCount = choices.length
  const remainingLots = lots.length - currentIndex - 1

  const phase = useMemo(() => {
    if (currentIndex < 3) return 'relaxed'
    if (currentIndex < 6) return 'tense'
    return 'critical'
  }, [currentIndex])

  const tensionHint = useMemo(() => {
    if (remainingChips === 0) {
      return { text: '筹码已用完，想给新拍品加价就先从前面撤码', type: 'warning' as const }
    }
    if (phase === 'relaxed') {
      return { text: `还剩 ${remainingChips} 筹码，可以先试探性出价`, type: 'info' as const }
    }
    if (phase === 'tense') {
      return { text: `还剩 ${remainingChips} 筹码，后面还有 ${remainingLots} 件拍品`, type: 'tense' as const }
    }
    return { text: `最后阶段，只剩 ${remainingChips} 筹码，真的要想清楚`, type: 'critical' as const }
  }, [remainingChips, phase, remainingLots])

  useEffect(() => {
    if (!currentLotId) return
    setDraftBid(Math.min(bids[currentLotId] || 0, perLotCap))
  }, [currentLotId, bids, perLotCap])

  const canCommitDraft = draftBid >= 0 && draftBid <= perLotCap && draftBid <= remainingChips + (bids[currentLotId] || 0)
  const conflictHint = currentLot?.conflict_hint || ''

  const setMilestone = useCallback((text: string) => {
    setCelebrationText(text)
    setTimeout(() => setCelebrationText(''), 1500)
  }, [])

  const updateBid = useCallback((lotId: string, nextValue: number) => {
    setBids((prev) => ({ ...prev, [lotId]: Math.max(0, Math.min(perLotCap, nextValue)) }))
  }, [perLotCap])

  const adjustDraftBid = (delta: number) => {
    if (!currentLotId) return
    const currentAssigned = bids[currentLotId] || 0
    const maxAllowed = Math.min(perLotCap, remainingChips + currentAssigned)
    const nextValue = Math.max(0, Math.min(maxAllowed, draftBid + delta))
    setDraftBid(nextValue)
    haptic(delta > 0 ? 'medium' : 'light')
  }

  const reduceAllocatedChip = (lotId: string) => {
    const currentValue = bids[lotId] || 0
    if (currentValue <= 0) return
    updateBid(lotId, currentValue - 1)
    haptic('light')
  }

  const increaseAllocatedChip = (lotId: string) => {
    const currentValue = bids[lotId] || 0
    if (currentValue >= perLotCap || remainingChips <= 0) return
    updateBid(lotId, currentValue + 1)
    haptic('medium')
  }

  const moveToNext = () => {
    setIsAnimatingOut(true)
    setTimeout(() => {
      if (currentIndex < lots.length - 1) {
        setCurrentIndex((prev) => prev + 1)
      } else {
        setCurrentIndex(lots.length)
      }
      setIsAnimatingOut(false)
    }, 250)
  }

  const commitCurrentBid = () => {
    if (!currentLotId || !canCommitDraft) {
      haptic('error')
      return
    }

    const previousBid = bids[currentLotId] || 0
    updateBid(currentLotId, draftBid)
    setChoices((prev) => [
      ...prev.filter((choice) => choice.lot_id !== currentLotId),
      { lot_id: currentLotId, chips: draftBid, timestamp: Date.now() },
    ])

    if (draftBid > previousBid) {
      setShowParticles(true)
      haptic('success')
      setTimeout(() => setShowParticles(false), 400)
    } else {
      haptic('medium')
    }

    const nextChosenCount = Object.values({ ...bids, [currentLotId]: draftBid }).filter((chips) => chips > 0).length
    if (completedCount + 1 === Math.floor(lots.length / 2)) {
      setMilestone('半程完成!')
    } else if (draftBid === perLotCap) {
      setMilestone('重注拍下!')
    } else if (nextChosenCount >= 4 && remainingChips - (draftBid - previousBid) <= 2) {
      setMilestone('筹码见底!')
    }

    moveToNext()
  }

  const handleSubmit = () => {
    onSubmit(lots.map((lot) => ({
      lot_id: lot.lot_id,
      chips: bids[lot.lot_id] || 0,
    })))
  }

  if (currentIndex >= lots.length) {
    return (
      <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-amber/10 to-gold-soft/20 animate-ambient-pulse" />
        <div className="relative z-10">
          <div className="flex items-center justify-center gap-2 mb-4">
            <Sparkles className="w-5 h-5 text-amber animate-pulse-soft" />
            <h3 className="text-xl font-bold text-center">{"封盘前最后调仓"}</h3>
            <Sparkles className="w-5 h-5 text-amber animate-pulse-soft" />
          </div>

          <div className="rounded-2xl bg-secondary/60 p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm text-muted-foreground">{"当前分配"}</div>
              <div className="text-sm font-medium text-foreground">
                {"剩余 "}<AnimatedNumber value={remainingChips} />{" / "}{total_chips}
              </div>
            </div>

            <div className="space-y-2">
              {lots.map((lot) => {
                const chips = bids[lot.lot_id] || 0
                return (
                  <div key={lot.lot_id} className="flex items-center gap-3 bg-white rounded-xl p-3 border border-border">
                    <div className="text-2xl">{lot.icon}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{lot.title}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => reduceAllocatedChip(lot.lot_id)}
                        disabled={chips <= 0}
                        className="w-8 h-8 rounded-full bg-secondary text-muted-foreground disabled:opacity-40"
                      >
                        <Minus className="w-4 h-4 mx-auto" />
                      </button>
                      <span className="w-8 text-center font-semibold tabular-nums">{chips}</span>
                      <button
                        onClick={() => increaseAllocatedChip(lot.lot_id)}
                        disabled={chips >= perLotCap || remainingChips <= 0}
                        className="w-8 h-8 rounded-full bg-amber text-white disabled:opacity-40"
                      >
                        <Plus className="w-4 h-4 mx-auto" />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <button
            onClick={handleSubmit}
            className={cn(
              'w-full h-14 rounded-xl text-base font-semibold',
              'bg-gradient-to-r from-amber to-gold text-white',
              'transition-all duration-200 active:scale-[0.98] touch-target shadow-lg shadow-amber/20',
            )}
          >
            {"封盘揭晓"}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'rounded-3xl border border-border bg-card p-6 shadow-sm will-change-transform relative overflow-hidden',
        isAnimatingOut ? 'animate-slide-scale-out' : 'animate-slide-scale-in',
      )}
    >
      {celebrationText && (
        <div className="absolute inset-0 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-amber text-white px-6 py-3 rounded-2xl font-bold text-lg animate-dimension-complete shadow-xl">
            {celebrationText}
          </div>
        </div>
      )}

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
              phase === 'critical' && 'animate-progress-glow',
            )}
            style={{ width: `${((currentIndex + 1) / lots.length) * 100}%` }}
          />
        </div>
      </div>

      {isDualMode && (
        <div className="rounded-xl px-3 py-2 mb-4 border bg-amber-soft/50 border-amber/20">
          <p className="text-xs text-muted-foreground text-center">
            {"秘密出价，封盘前没人知道你投了多少"}
          </p>
        </div>
      )}

      <div
        className={cn(
          'rounded-xl px-4 py-3 mb-4 border transition-all duration-300',
          tensionHint.type === 'critical' && 'bg-destructive/10 border-destructive/30 animate-pulse-soft',
          tensionHint.type === 'tense' && 'bg-amber-soft/60 border-amber/30',
          tensionHint.type === 'warning' && 'bg-amber-soft/60 border-amber/30',
          tensionHint.type === 'info' && 'bg-secondary/60 border-border',
        )}
      >
        <p
          className={cn(
            'text-sm text-center font-medium flex items-center justify-center gap-2',
            tensionHint.type === 'critical' && 'text-destructive',
            tensionHint.type !== 'critical' && 'text-muted-foreground',
          )}
        >
          {tensionHint.type !== 'info' && <AlertTriangle className="w-4 h-4" />}
          {tensionHint.text}
        </p>
      </div>

      <div
        className={cn(
          'relative rounded-2xl p-5 border-2 mb-4 transition-all duration-300',
          'bg-gradient-to-br from-amber-soft/40 to-gold-soft/40',
          showParticles && 'animate-elastic-pop',
        )}
        style={{ borderColor: currentLot?.theme_color || 'var(--amber)' }}
      >
        <ParticleBurst trigger={showParticles} color="var(--amber)" />

        <div className="text-center mb-4">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-amber/10 to-gold/10 text-5xl animate-scale-in">
            {currentLot?.icon || '?'}
          </div>
        </div>

        <div className="text-center mb-4">
          <h4 className="text-xl font-bold text-foreground mb-2 text-balance animate-fade-in">
            {currentLot?.title}
          </h4>
          <p className="text-sm text-muted-foreground italic leading-relaxed text-pretty animate-fade-in" style={{ animationDelay: '100ms' }}>
            {`"${currentLot?.interpretation}"`}
          </p>
        </div>

        {conflictHint && phase !== 'relaxed' && (
          <div className="rounded-xl px-3 py-2 border bg-gold-soft/50 border-gold/20 animate-fade-in" style={{ animationDelay: '200ms' }}>
            <p className="text-xs text-muted-foreground text-center flex items-center justify-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5 text-gold" />
              {conflictHint}
            </p>
          </div>
        )}

        <div className="mt-5 rounded-2xl bg-background/90 p-4 border border-border">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-muted-foreground">给这件拍品出多少筹码？</div>
            <div className="text-sm font-semibold text-foreground">
              {draftBid} / {perLotCap}
            </div>
          </div>

          <div className="flex items-center justify-center gap-3 mb-4">
            <button
              onClick={() => adjustDraftBid(-1)}
              disabled={draftBid <= 0}
              className="w-11 h-11 rounded-full bg-secondary text-muted-foreground disabled:opacity-40"
            >
              <Minus className="w-5 h-5 mx-auto" />
            </button>
            <div className="min-w-[96px] text-center">
              <div className="text-3xl font-bold text-foreground tabular-nums">{draftBid}</div>
              <div className="text-xs text-muted-foreground">当前出价</div>
            </div>
            <button
              onClick={() => adjustDraftBid(1)}
              disabled={draftBid >= Math.min(perLotCap, remainingChips + (bids[currentLotId] || 0))}
              className="w-11 h-11 rounded-full bg-amber text-white disabled:opacity-40"
            >
              <Plus className="w-5 h-5 mx-auto" />
            </button>
          </div>

          <div className="grid grid-cols-4 gap-2">
            {[0, 1, 2, 3].map((value) => {
              const disabled = value > perLotCap || value > remainingChips + (bids[currentLotId] || 0)
              return (
                <button
                  key={value}
                  onClick={() => {
                    setDraftBid(value)
                    haptic(value === 0 ? 'light' : 'medium')
                  }}
                  disabled={disabled}
                  className={cn(
                    'h-10 rounded-xl text-sm font-medium transition-all',
                    draftBid === value
                      ? 'bg-amber text-white shadow-md'
                      : 'bg-secondary text-muted-foreground',
                    disabled && 'opacity-40 cursor-not-allowed',
                  )}
                >
                  {value === 0 ? '不投' : `${value} 筹码`}
                </button>
              )
            })}
          </div>
        </div>

        {revisableLots.length > 0 && remainingChips === 0 && draftBid > (bids[currentLotId] || 0) && (
          <div className="mt-4 rounded-xl p-4 border bg-destructive/5 border-destructive/20 animate-fade-in">
            <p className="text-xs text-muted-foreground text-center mb-3 font-medium">
              {"想继续加码，就先从前面的选择里撤一点："}
            </p>
            <div className="flex flex-col gap-2">
              {revisableLots.map((lot) => (
                <button
                  key={lot.lot_id}
                  onClick={() => reduceAllocatedChip(lot.lot_id)}
                  className="px-4 py-3 rounded-xl text-sm font-medium bg-background border border-border hover:bg-amber-soft hover:border-amber/30 transition-all touch-target active:scale-[0.98] flex items-center justify-between gap-2"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-lg">{lot.icon}</span>
                    <span>{lot.title}</span>
                  </span>
                  <span className="text-muted-foreground">-{bids[lot.lot_id]}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button
          onClick={() => {
            setDraftBid(0)
            commitCurrentBid()
          }}
          className="flex-1 h-14 rounded-xl text-base font-semibold bg-secondary text-muted-foreground hover:bg-secondary/80 active:scale-[0.98] transition-all touch-target"
        >
          {"这件不投"}
        </button>
        <button
          onClick={commitCurrentBid}
          disabled={!canCommitDraft}
          className={cn(
            'flex-1 h-14 rounded-xl text-base font-semibold transition-all touch-target',
            canCommitDraft
              ? 'bg-gradient-to-r from-amber to-gold text-white shadow-lg shadow-amber/20 active:scale-[0.98]'
              : 'bg-secondary text-muted-foreground opacity-60 cursor-not-allowed',
          )}
        >
          {currentIndex === lots.length - 1 ? '进入封盘前调整' : '锁定这件'}
        </button>
      </div>

      {(completedCount > 0 || chosenLots.length > 0) && (
        <div className="mt-4 pt-4 border-t border-border">
          <button
            onClick={() => setIsSummaryExpanded(!isSummaryExpanded)}
            className="w-full flex items-center justify-between text-xs text-muted-foreground mb-2 touch-target"
          >
            <span className="font-medium">
              {"已看过 "}<AnimatedNumber value={completedCount} />{" 件，已投 "}<AnimatedNumber value={chosenLots.length} />{" 件"}
            </span>
            {isSummaryExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {isSummaryExpanded && (
            <div className="space-y-2 animate-fade-in">
              {chosenLots.length === 0 ? (
                <div className="text-xs text-muted-foreground">{"还没有真正下筹码的拍品"}</div>
              ) : (
                chosenLots.map((lot) => (
                  <div key={lot.lot_id} className="flex items-center gap-3 rounded-xl bg-secondary/50 p-2.5">
                    <span className="text-lg">{lot.icon}</span>
                    <span className="flex-1 text-xs font-medium truncate">{lot.title}</span>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => reduceAllocatedChip(lot.lot_id)}
                        className="w-7 h-7 rounded-full bg-background text-muted-foreground"
                      >
                        <Minus className="w-3.5 h-3.5 mx-auto" />
                      </button>
                      <span className="w-6 text-center text-xs font-semibold tabular-nums">{lot.chips}</span>
                      <button
                        onClick={() => increaseAllocatedChip(lot.lot_id)}
                        disabled={lot.chips >= perLotCap || remainingChips <= 0}
                        className="w-7 h-7 rounded-full bg-amber text-white disabled:opacity-40"
                      >
                        <Plus className="w-3.5 h-3.5 mx-auto" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
