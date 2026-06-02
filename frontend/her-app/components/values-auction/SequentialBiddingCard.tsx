/**
 * 价值观拍卖会逐个展示模式卡片
 *
 * v3.0 游戏化改进版：
 * - 一次只展示一个拍品（真实拍卖会体验）
 * - 用户选择保留/放弃后，展示下一个
 * - 动态提示剩余名额（紧张感设计）
 * - 进度显示（"第3件拍品（共9件）"）
 * - 冲突提示（帮助理解取舍）
 */

import React, { useState, useMemo } from 'react'
import { Check, X, AlertTriangle, Lightbulb, ChevronDown, ChevronUp } from 'lucide-react'
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

export function SequentialBiddingCard({ card, onSubmit, isDualMode }: Props) {
  const { lots_data } = card
  const { lots } = lots_data

  // 当前展示的拍品索引（从0开始）
  const [currentIndex, setCurrentIndex] = useState(0)

  // 选择记录：已保留的拍品、已放弃的拍品
  const [choices, setChoices] = useState<ChoiceRecord[]>([])
  
  // 已选区折叠状态
  const [isChoicesExpanded, setIsChoicesExpanded] = useState(false)

  // 名额限制：最终只能保留3个
  const MAX_KEEP = 3

  // 计算状态
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

  // 当前拍品
  const currentLot = lots[currentIndex]

  // 是否名额已满
  const isSlotsFull = keptLots.length >= MAX_KEEP

  // 阶段判断：宽松期、紧张期、决断期
  const phase = useMemo(() => {
    if (currentIndex < 3) return 'relaxed' // 宽松期
    if (currentIndex < 6) return 'tense'    // 紧张期
    return 'critical'                       // 决断期
  }, [currentIndex])

  // 紧张感提示文案 - 简化版
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

  // 冲突提示文案（基于拍品的 conflict_hint 字段）
  const conflictHint = currentLot?.conflict_hint || ''

  // 处理保留
  const handleKeep = () => {
    if (!currentLot) return

    // 如果名额已满，需要替换
    if (isSlotsFull) {
      handleDiscard()
      return
    }

    // 记录选择
    setChoices(prev => [...prev, {
      lot_id: currentLot.lot_id,
      choice: 'keep',
      timestamp: Date.now()
    }])

    // 展示下一个拍品
    moveToNext()
  }

  // 处理放弃
  const handleDiscard = () => {
    if (!currentLot) return

    // 记录选择
    setChoices(prev => [...prev, {
      lot_id: currentLot.lot_id,
      choice: 'discard',
      timestamp: Date.now()
    }])

    // 展示下一个拍品
    moveToNext()
  }

  // 移动到下一个拍品
  const moveToNext = () => {
    if (currentIndex < lots.length - 1) {
      setCurrentIndex(prev => prev + 1)
    } else {
      // 所有拍品都已展示，提交结果
      handleSubmit()
    }
  }

  // 提交结果
  const handleSubmit = () => {
    // 转换为出价格式
    const bids = lots.map(lot => ({
      lot_id: lot.lot_id,
      chips: keptLots.includes(lot.lot_id) ? 3 : 0  // 保留的给3筹码，放弃的给0
    }))

    onSubmit(bids)
  }

  // 替换逻辑（名额已满时）
  const handleReplace = (targetLotId: string) => {
    // 从已保留中移除目标拍品
    setChoices(prev => prev.filter(c => c.lot_id !== targetLotId))

    // 将当前拍品加入保留
    setChoices(prev => [...prev, {
      lot_id: currentLot.lot_id,
      choice: 'keep',
      timestamp: Date.now()
    }])

    // 展示下一个拍品
    moveToNext()
  }

  // 如果所有拍品都已展示，显示结果预告
  if (currentIndex >= lots.length) {
    return (
      <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in">
        <h3 className="text-xl font-semibold text-center mb-4">{"取舍完成"}</h3>

        <div className="rounded-2xl bg-secondary/60 p-4 mb-4">
          <div className="text-sm text-muted-foreground mb-2">{"你保留了："}</div>
          {keptLots.map(lotId => {
            const lot = lots.find(l => l.lot_id === lotId)
            return (
              <div key={lotId} className="flex items-center gap-2 text-foreground font-medium py-1">
                <Check className="w-4 h-4 text-amber" />
                <span>{lot?.title}</span>
              </div>
            )
          })}
          {keptLots.length === 0 && (
            <div className="text-muted-foreground text-sm">{"没有保留任何拍品"}</div>
          )}
        </div>

        <button
          onClick={handleSubmit}
          className={cn(
            'w-full h-12 rounded-xl text-base font-medium',
            'bg-amber hover:bg-amber/90 text-white',
            'transition-all duration-200 active:scale-[0.98] touch-target'
          )}
        >
          {"封盘揭晓"}
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-fade-in-up will-change-transform">
      {/* 进度指示器 - 水平条形 */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
          <span>{"第 "}{currentIndex + 1}{" 件"}</span>
          <span>{"共 "}{lots.length}{" 件"}</span>
        </div>
        <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
          <div 
            className="h-full bg-amber rounded-full transition-all duration-300"
            style={{ width: `${((currentIndex + 1) / lots.length) * 100}%` }}
          />
        </div>
        {/* 小圆点指示已选择状态 */}
        <div className="flex justify-center gap-1.5 mt-2">
          {lots.map((lot, i) => {
            const choice = choices.find(c => c.lot_id === lot.lot_id)
            const isCurrent = i === currentIndex
            const isKept = choice?.choice === 'keep'
            const isDiscarded = choice?.choice === 'discard'
            
            return (
              <div
                key={lot.lot_id}
                className={cn(
                  'w-2 h-2 rounded-full transition-all duration-200',
                  isCurrent && 'w-4 bg-amber animate-pulse',
                  !isCurrent && isKept && 'bg-amber',
                  !isCurrent && isDiscarded && 'bg-secondary',
                  !isCurrent && !choice && 'bg-border'
                )}
              />
            )
          })}
        </div>
      </div>

      {/* 双人模式提示 */}
      {isDualMode && (
        <div className={cn(
          'rounded-xl px-3 py-2 mb-4 border',
          'bg-amber-soft/50 border-amber/20'
        )}>
          <p className="text-xs text-muted-foreground text-center">
            {"秘密取舍，封盘前没人知道你选了什么"}
          </p>
        </div>
      )}

      {/* 紧张感提示 */}
      <div className={cn(
        'rounded-xl px-4 py-2.5 mb-4 border',
        tensionHint.type === 'critical' && 'bg-destructive/10 border-destructive/20',
        tensionHint.type === 'tense' && 'bg-amber-soft/60 border-amber/30',
        tensionHint.type === 'warning' && 'bg-amber-soft/60 border-amber/30',
        tensionHint.type === 'info' && 'bg-secondary/60 border-border'
      )}>
        <p className={cn(
          'text-sm text-center font-medium',
          tensionHint.type === 'critical' && 'text-destructive',
          tensionHint.type === 'tense' && 'text-amber',
          tensionHint.type === 'warning' && 'text-amber',
          tensionHint.type === 'info' && 'text-muted-foreground'
        )}>
          {tensionHint.type !== 'info' && <AlertTriangle className="w-4 h-4 inline mr-1.5 -mt-0.5" />}
          {tensionHint.text}
        </p>
      </div>

      {/* 当前拍品大卡 */}
      <div
        className={cn(
          'rounded-2xl p-5 border-2 mb-4 transition-all duration-300',
          'bg-gradient-to-br from-amber-soft/30 to-gold-soft/30'
        )}
        style={{ borderColor: currentLot?.theme_color || 'var(--amber)' }}
      >
        {/* 拍品图标 */}
        <div className="text-center mb-3">
          <div className="text-4xl mb-1" role="img" aria-label={currentLot?.title}>
            {currentLot?.icon || '?'}
          </div>
        </div>

        {/* 拍品标题 */}
        <div className="text-center mb-3">
          <h4 className="text-lg font-semibold text-foreground mb-1.5 text-balance">
            {currentLot?.title}
          </h4>
          <p className="text-sm text-muted-foreground italic leading-relaxed text-pretty">
            {`"${currentLot?.interpretation}"`}
          </p>
        </div>

        {/* 冲突提示 */}
        {conflictHint && phase !== 'relaxed' && (
          <div className={cn(
            'rounded-xl px-3 py-2 border',
            'bg-gold-soft/50 border-gold/20'
          )}>
            <p className="text-xs text-muted-foreground text-center flex items-center justify-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5 text-gold" />
              {conflictHint}
            </p>
          </div>
        )}

        {/* 名额已满时的替换提示 - 改为底部抽屉样式 */}
        {isSlotsFull && (
          <div className={cn(
            'mt-3 rounded-xl p-3 border',
            'bg-destructive/5 border-destructive/20'
          )}>
            <p className="text-xs text-muted-foreground text-center mb-2.5">
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
                      'px-3 py-2 rounded-xl text-sm',
                      'bg-background border border-border',
                      'hover:bg-secondary hover:border-amber/30',
                      'transition-all touch-target active:scale-[0.98]'
                    )}
                  >
                    {"替换："}{lot?.title}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* 取舍按钮 */}
      <div className="flex gap-3">
        <button
          onClick={handleDiscard}
          className={cn(
            'flex-1 h-12 rounded-xl text-base font-medium',
            'bg-secondary text-muted-foreground',
            'flex items-center justify-center gap-2',
            'hover:bg-secondary/80 active:scale-[0.98]',
            'transition-all touch-target'
          )}
        >
          <X className="w-4 h-4" />
          {"放弃"}
        </button>
        <button
          onClick={handleKeep}
          disabled={isSlotsFull}
          className={cn(
            'flex-1 h-12 rounded-xl text-base font-medium',
            'flex items-center justify-center gap-2',
            'transition-all touch-target',
            isSlotsFull
              ? 'bg-secondary text-muted-foreground cursor-not-allowed opacity-60'
              : 'bg-amber hover:bg-amber/90 text-white active:scale-[0.98]'
          )}
        >
          <Check className="w-4 h-4" />
          {isSlotsFull ? '名额已满' : '保留'}
        </button>
      </div>

      {/* 已选择区（可折叠） */}
      {choices.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <button
            onClick={() => setIsChoicesExpanded(!isChoicesExpanded)}
            className="w-full flex items-center justify-between text-xs text-muted-foreground mb-2 touch-target"
          >
            <span>{"已选择 "}{choices.length}{" 件"}</span>
            {isChoicesExpanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
          
          {isChoicesExpanded && (
            <div className="flex gap-4 animate-fade-in">
              {/* 已保留 */}
              <div className="flex-1">
                <div className="text-xs text-amber mb-1.5">
                  {"保留（"}{keptLots.length}{"/"}{MAX_KEEP}{"）"}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {keptLots.map(lotId => {
                    const lot = lots.find(l => l.lot_id === lotId)
                    return (
                      <div 
                        key={lotId} 
                        className="px-2 py-1 bg-amber-soft rounded-lg text-xs text-foreground"
                      >
                        {lot?.icon} {lot?.title?.substring(0, 6)}...
                      </div>
                    )
                  })}
                  {keptLots.length === 0 && (
                    <span className="text-xs text-muted-foreground">{"暂无"}</span>
                  )}
                </div>
              </div>
              {/* 已放弃 */}
              <div className="flex-1">
                <div className="text-xs text-muted-foreground mb-1.5">
                  {"放弃（"}{discardedLots.length}{"）"}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {discardedLots.slice(-3).map(lotId => {
                    const lot = lots.find(l => l.lot_id === lotId)
                    return (
                      <div 
                        key={lotId} 
                        className="px-2 py-1 bg-secondary rounded-lg text-xs text-muted-foreground"
                      >
                        {lot?.title?.substring(0, 6)}...
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
