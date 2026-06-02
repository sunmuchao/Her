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

import React, { useState, useMemo, useEffect } from 'react'
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

  // 紧张感提示文案
  const tensionHint = useMemo(() => {
    if (isSlotsFull) {
      return `⚠️ 名额已满！后面的拍品只能放弃，或者替换之前的选择`
    }
    if (phase === 'relaxed') {
      return `你已保留 ${keptLots.length} 件，还能保留 ${remainingSlots} 件`
    }
    if (phase === 'tense') {
      return `⚠️ 名额紧张！你已保留 ${keptLots.length} 件，还能保留 ${remainingSlots} 件，还剩 ${remainingLots} 件拍品要看，后面的拍品可能更好，要慎重选择`
    }
    return `⚠️ 最后名额！你已保留 ${keptLots.length} 件，还能保留 ${remainingSlots} 件，还剩 ${remainingLots} 件拍品要看`
  }, [keptLots.length, remainingSlots, remainingLots, phase, isSlotsFull])

  // 冲突提示文案（基于拍品的 conflict_hint 字段）
  const conflictHint = currentLot?.conflict_hint || ''

  // 处理保留
  const handleKeep = () => {
    if (!currentLot) return

    // 如果名额已满，需要替换
    if (isSlotsFull) {
      // 弹出替换选择界面（简化版：直接放弃当前拍品）
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

  // 进度可视化
  const progressVisual = useMemo(() => {
    return lots.map((lot, i) => {
      const choice = choices.find(c => c.lot_id === lot.lot_id)
      if (i < currentIndex) {
        return choice?.choice === 'keep' ? '✓' : '⚫'
      }
      if (i === currentIndex) return '?'
      return '·'
    })
  }, [lots, currentIndex, choices])

  // 如果所有拍品都已展示，显示结果预告
  if (currentIndex >= lots.length) {
    return (
      <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200">
        <h3 className="text-xl font-bold text-amber-900 text-center mb-4">取舍完成</h3>

        <div className="bg-white rounded-xl p-4 mb-4">
          <div className="text-sm text-amber-800 mb-2">你保留了：</div>
          {keptLots.map(lotId => {
            const lot = lots.find(l => l.lot_id === lotId)
            return (
              <div key={lotId} className="text-amber-900 font-medium">
                ✓ {lot?.title}
              </div>
            )
          })}
        </div>

        <button
          onClick={handleSubmit}
          className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all"
        >
          封盘揭晓
        </button>
      </div>
    )
  }

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200 animate-fade-in">
      {/* 进度条 */}
      <div className="mb-4">
        <div className="flex justify-center gap-1 mb-2">
          {progressVisual.map((symbol, i) => (
            <div
              key={i}
              className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                symbol === '✓' ? 'bg-amber-400 text-white' :
                symbol === '⚫' ? 'bg-gray-300 text-gray-600' :
                symbol === '?' ? 'bg-orange-400 text-white animate-pulse' :
                'bg-gray-100 text-gray-400'
              }`}
            >
              {i + 1}
            </div>
          ))}
        </div>
        <div className="text-center text-sm text-amber-700">
          第 {currentIndex + 1} 件拍品（共 {lots.length} 件）
        </div>
      </div>

      {/* 双人模式提示 */}
      {isDualMode && (
        <div className="bg-orange-100 rounded-lg p-2 mb-4">
          <p className="text-xs text-orange-700 text-center">
            ⚠️ 秘密取舍，封盘前没人知道你选了什么
          </p>
        </div>
      )}

      {/* 紧张感提示 */}
      <div className={`rounded-lg p-3 mb-4 ${
        phase === 'critical' ? 'bg-red-50 border border-red-200' :
        phase === 'tense' ? 'bg-orange-50 border border-orange-200' :
        'bg-amber-50 border border-amber-100'
      }`}>
        <p className={`text-sm text-center ${
          phase === 'critical' ? 'text-red-700' :
          phase === 'tense' ? 'text-orange-700' :
          'text-amber-700'
        }`}>
          {tensionHint}
        </p>
      </div>

      {/* 当前拍品大卡 */}
      <div
        className="bg-white rounded-2xl p-6 shadow-lg border-2 mb-4 transition-all duration-300 hover:shadow-xl"
        style={{ borderColor: currentLot?.theme_color || '#F59E0B' }}
      >
        {/* 拍品图标 */}
        <div className="text-center mb-4">
          <div className="text-5xl mb-2">{currentLot?.icon || '💰'}</div>
        </div>

        {/* 拍品标题 */}
        <div className="text-center mb-4">
          <h4 className="text-xl font-bold text-amber-900 mb-2">
            {currentLot?.title}
          </h4>
          <p className="text-sm text-amber-600 italic">
            "{currentLot?.interpretation}"
          </p>
        </div>

        {/* 冲突提示 */}
        {conflictHint && phase !== 'relaxed' && (
          <div className="bg-orange-50 rounded-lg p-3 mb-4 border border-orange-100">
            <p className="text-xs text-orange-700 text-center">
              💡 {conflictHint}
            </p>
          </div>
        )}

        {/* 名额已满时的替换提示 */}
        {isSlotsFull && (
          <div className="bg-red-50 rounded-lg p-3 mb-4 border border-red-200">
            <p className="text-xs text-red-700 text-center mb-2">
              名额已满！如果保留这件，需要替换之前的选择：
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {keptLots.map(lotId => {
                const lot = lots.find(l => l.lot_id === lotId)
                return (
                  <button
                    key={lotId}
                    onClick={() => handleReplace(lotId)}
                    className="px-3 py-1 bg-white border border-red-200 rounded-lg text-xs text-red-700 hover:bg-red-100 transition-all"
                  >
                    替换：{lot?.title?.substring(0, 10)}...
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* 取舍按钮 */}
      <div className="flex gap-4">
        <button
          onClick={handleDiscard}
          className="flex-1 py-3 bg-gray-100 text-gray-700 font-medium rounded-xl shadow-md hover:bg-gray-200 hover:shadow-lg active:scale-[0.98] transition-all"
        >
          放弃
        </button>
        <button
          onClick={handleKeep}
          disabled={isSlotsFull}
          className={`flex-1 py-3 font-medium rounded-xl shadow-md transition-all ${
            isSlotsFull
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-gradient-to-r from-amber-500 to-orange-500 text-white hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]'
          }`}
        >
          {isSlotsFull ? '名额已满' : '保留'}
        </button>
      </div>

      {/* 已选择区（可选显示） */}
      {choices.length > 0 && (
        <div className="mt-4 pt-4 border-t border-amber-100">
          <div className="flex gap-4">
            {/* 已保留 */}
            <div className="flex-1">
              <div className="text-xs text-amber-700 mb-1">已保留（{keptLots.length}/{MAX_KEEP}）：</div>
              <div className="flex flex-wrap gap-1">
                {keptLots.map(lotId => {
                  const lot = lots.find(l => l.lot_id === lotId)
                  return (
                    <div key={lotId} className="px-2 py-1 bg-amber-100 rounded text-xs text-amber-700">
                      {lot?.icon} {lot?.title?.substring(0, 8)}...
                    </div>
                  )
                })}
              </div>
            </div>
            {/* 已放弃 */}
            <div className="flex-1">
              <div className="text-xs text-gray-500 mb-1">已放弃（{discardedLots.length}）：</div>
              <div className="flex flex-wrap gap-1">
                {discardedLots.slice(-3).map(lotId => {
                  const lot = lots.find(l => l.lot_id === lotId)
                  return (
                    <div key={lotId} className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-500">
                      {lot?.title?.substring(0, 8)}...
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}