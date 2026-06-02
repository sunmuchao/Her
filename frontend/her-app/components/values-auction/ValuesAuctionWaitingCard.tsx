/**
 * 价值观拍卖会等待对方卡片
 *
 * v3.0 双人盲拍升级版：
 * - 封盘等待页：左侧显示你的取舍结果（已封盘），右侧显示TA的状态
 * - 主持人提示：强调"盲拍对照"的紧张感
 * - 更好的视觉设计和文案
 */

import React, { useEffect, useState } from 'react'
import type { ValuesAuctionWaitingCard, ValuesLot } from '@/lib/api/endpoints/valuesAuction'
import { checkValuesAuctionStatus } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesAuctionWaitingCard
  userKey: string
  onMatchReady: (matchCard: any) => void
  onContinueChat?: () => void
  lots?: ValuesLot[]  // 新增：拍品列表（用于获取详细信息）
}

export function ValuesAuctionWaitingCard({ card, userKey, onMatchReady, onContinueChat, lots }: Props) {
  const { waiting_data, session_id } = card
  const { message, your_result, partner_status } = waiting_data

  const [isPolling, setIsPolling] = useState(true)
  const [countdown, setCountdown] = useState(3)
  const [partnerDone, setPartnerDone] = useState(partner_status === 'done')

  // 轮询检查状态
  useEffect(() => {
    if (!isPolling) return

    const pollInterval = setInterval(async () => {
      try {
        const result = await checkValuesAuctionStatus({
          sessionId: session_id,
          userKey: userKey,
        })

        if (result.status === 'both_done' && result.card_type === 'values_match_analysis') {
          setIsPolling(false)
          onMatchReady(result)
        }

        // 更新对方状态
        if (result.partner_status === 'done') {
          setPartnerDone(true)
        }
      } catch (error) {
        console.error('Poll error:', error)
      }
    }, 3000) // 每3秒轮询

    return () => clearInterval(pollInterval)
  }, [isPolling, session_id, userKey, onMatchReady])

  // 倒计时动画
  useEffect(() => {
    if (!isPolling) return

    const timer = setInterval(() => {
      setCountdown(prev => prev > 0 ? prev - 1 : 3)
    }, 1000)

    return () => clearInterval(timer)
  }, [isPolling])

  // 获取拍品详细信息
  const getLotInfo = (title: string) => {
    if (!lots) return null
    return lots.find(l => l.title === title)
  }

  return (
    <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-2xl p-6 shadow-lg border border-blue-200 animate-fade-in">
      {/* 标题：盲拍对照模式 */}
      <div className="text-center mb-6">
        <div className="text-3xl mb-2">
          🔒 vs ⏳
        </div>
        <h2 className="text-xl font-bold text-blue-900">盲拍对照模式</h2>
        <p className="text-blue-600 mt-2 text-sm font-medium">
          你和 TA 各自秘密取舍，封盘后同时揭晓
        </p>
      </div>

      {/* 双人对照布局 */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* 左侧：你的选择（已封盘） */}
        <div className="bg-white rounded-xl p-4 border-2 border-blue-300 shadow-sm">
          <div className="text-center mb-3">
            <div className="text-2xl mb-1">🔒</div>
            <div className="text-sm font-bold text-blue-800">你的选择</div>
            <div className="text-xs text-blue-600">已封盘</div>
          </div>

          <div className="space-y-2">
            {your_result.top3.map((item, i) => {
              const lotInfo = getLotInfo(item.title)
              return (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <div className="text-lg">{lotInfo?.icon || '💰'}</div>
                  <div className="flex-1 text-blue-700 truncate">
                    {item.title?.substring(0, 15)}...
                  </div>
                  <div className="text-blue-500 font-medium">{item.chips}</div>
                </div>
              )
            })}
          </div>

          <div className="mt-3 pt-2 border-t border-blue-100">
            <div className="text-xs text-blue-600 font-medium text-center">
              {your_result.value_type}
            </div>
          </div>
        </div>

        {/* 右侧：TA的状态 */}
        <div className={`rounded-xl p-4 border-2 shadow-sm ${
          partnerDone ? 'bg-white border-green-300' : 'bg-gray-50 border-gray-200'
        }`}>
          <div className="text-center mb-3">
            <div className="text-2xl mb-1">
              {partnerDone ? '🔒' : '⏳'}
            </div>
            <div className={`text-sm font-bold ${partnerDone ? 'text-green-800' : 'text-gray-600'}`}>
              TA 的状态
            </div>
            <div className={`text-xs ${partnerDone ? 'text-green-600' : 'text-gray-500'}`}>
              {partnerDone ? '已封盘' : '仍在取舍中'}
            </div>
          </div>

          {partnerDone ? (
            <div className="text-center text-green-600 text-sm">
              ✓ 已完成，等待揭晓
            </div>
          ) : (
            <div className="text-center text-gray-500 text-sm">
              对方仍在取舍...
              <div className="mt-2 animate-pulse">
                ⏳ 等待中
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 主持人提示 */}
      <div className="bg-gradient-to-r from-blue-100 to-indigo-100 rounded-lg p-4 mb-4 border border-blue-200">
        <div className="text-center mb-2">
          <div className="text-sm font-bold text-blue-800">💡 主持人提示</div>
        </div>
        <div className="space-y-1 text-sm text-blue-700 text-center">
          <div>• TA 看不到你的选择，你也看不到 TA 的</div>
          <div>• 封盘后将同时揭晓：你们抢的是不是同一种人生</div>
          <div>• 会看到共鸣点、分歧点、最危险的冲突</div>
        </div>
      </div>

      {/* 等待提示 */}
      <div className="bg-blue-50 rounded-lg p-3 mb-4">
        <div className="text-blue-800 font-medium mb-2 text-sm text-center">
          揭晓时你们会看到：
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-blue-700">
          <div className="bg-white rounded p-2 text-center">
            💫 共鸣拍品
          </div>
          <div className="bg-white rounded p-2 text-center">
            ⚡ 分歧拍品
          </div>
          <div className="bg-white rounded p-2 text-center">
            ⚠️ 冲突风险
          </div>
          <div className="bg-white rounded p-2 text-center">
            💡 匹配建议
          </div>
        </div>
      </div>

      {/* 轮询状态 */}
      <div className="text-center mb-4">
        <div className="inline-flex items-center gap-2 px-3 py-2 bg-blue-50 rounded-full">
          <div
            key={countdown}
            className="w-6 h-6 bg-blue-200 rounded-full flex items-center justify-center text-blue-700 font-bold text-xs animate-scale-in"
          >
            {countdown}
          </div>
          <span className="text-blue-600 text-sm">秒后刷新</span>
        </div>
      </div>

      {/* 继续聊天按钮 */}
      {onContinueChat && (
        <button
          onClick={onContinueChat}
          className="w-full py-3 bg-gray-100 text-gray-600 font-medium rounded-xl hover:bg-gray-200 transition-all"
        >
          先聊别的（后台等待）
        </button>
      )}
    </div>
  )
}