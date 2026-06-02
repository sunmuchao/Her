/**
 * 双人三观匹配分析卡片
 *
 * v3.0 双人揭晓仪式升级版：
 * - 先揭晓你的Top3（翻牌动效）
 * - 再揭晓TA的Top3（翻牌动效）
 * - 再揭晓共鸣拍品（双方都保留的）
 * - 再揭晓分歧拍品（一方保留，一方放弃）
 * - 最后揭晓冲突风险（一方最看重，一方放弃）
 * - 更好的视觉设计和文案
 */

import React, { useState, useEffect, useMemo } from 'react'
import type { ValuesMatchAnalysisCard, ValuesLot } from '@/lib/api/endpoints/valuesAuction'
import { HIDDEN_VALUE_LABELS } from '@/lib/api/endpoints/valuesAuction'

type Props = {
  card: ValuesMatchAnalysisCard
  onContinue?: () => void
  currentUserKey?: string  // 当前用户的key，用于区分"你"和"对方"
  lots?: ValuesLot[]  // 新增：拍品列表（用于获取详细信息）
}

export function ValuesMatchAnalysisCardComponent({ card, onContinue, currentUserKey, lots }: Props) {
  const { match_data } = card
  const {
    user1,
    user2,
    match_type,
    common_lots,
    common_hidden_values,
    misalignments,
    conflicts,
  } = match_data

  // 揭晓阶段状态（0-4）
  const [revealPhase, setRevealPhase] = useState(0)

  // 自动揭晓（每阶段延迟1秒）
  useEffect(() => {
    if (revealPhase < 4) {
      const timer = setTimeout(() => {
        setRevealPhase(prev => prev + 1)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [revealPhase])

  // 判断当前用户是 user1 还是 user2
  const isUser1 = currentUserKey === user1.user_key
  const currentUser = isUser1 ? user1 : user2
  const partnerUser = isUser1 ? user2 : user1

  // 获取拍品详细信息
  const getLotInfo = (lotId: string) => {
    if (!lots) return null
    return lots.find(l => l.lot_id === lotId)
  }

  // 计算共鸣拍品（双方都保留且筹码都>=2）
  const resonantLots = useMemo(() => {
    if (!common_lots) return []
    return common_lots.map(lotId => {
      const lotInfo = getLotInfo(lotId)
      const user1Lot = user1.top3.find(l => l.lot_id === lotId)
      const user2Lot = user2.top3.find(l => l.lot_id === lotId)
      return {
        lot_id: lotId,
        title: lotInfo?.title || user1Lot?.title || '',
        icon: lotInfo?.icon || '💰',
        theme_color: lotInfo?.theme_color || '#F59E0B',
        user1_chips: user1Lot?.chips || 0,
        user2_chips: user2Lot?.chips || 0,
      }
    })
  }, [common_lots, lots, user1, user2])

  // 计算分歧拍品（一方保留，一方放弃或筹码很低）
  const divergentLots = useMemo(() => {
    if (!misalignments) return []
    return misalignments.map(m => {
      const lotInfo = getLotInfo(m.lot_id || '')
      return {
        lot_id: m.lot_id || '',
        title: lotInfo?.title || '',
        icon: lotInfo?.icon || '💰',
        type: m.type,
        description: m.description,
      }
    })
  }, [misalignments, lots])

  // 匹配类型颜色
  const matchColor = getMatchColor(match_type)

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200 animate-fade-in">
      {/* 标题：同时揭晓仪式 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          🎭
        </div>
        <h2 className="text-xl font-bold text-amber-900">同时揭晓仪式</h2>
        <p className="text-amber-600 mt-2 text-sm font-medium">
          你们抢的是不是同一种人生？
        </p>
      </div>

      {/* Phase 0: 你的Top3揭晓 */}
      {revealPhase >= 0 && (
        <div className="mb-6 animate-fade-in">
          <div className="bg-white rounded-xl p-4 border-2 border-amber-300 shadow-md">
            <div className="text-center mb-3">
              <div className="text-sm font-bold text-amber-800 mb-2">你的 Top3</div>
            </div>
            <div className="space-y-2">
              {currentUser.top3.map((lot, i) => {
                const lotInfo = getLotInfo(lot.lot_id)
                return (
                  <div
                    key={lot.lot_id}
                    className="flex items-center gap-3 p-2 rounded-lg border transition-all hover:shadow-md"
                    style={{
                      borderColor: lotInfo?.theme_color || '#F59E0B',
                      animationDelay: `${i * 0.2}s`
                    }}
                  >
                    <div className="text-2xl">{lotInfo?.icon || '💰'}</div>
                    <div className="flex-1">
                      <div className="text-sm font-bold text-amber-900">
                        第 {i + 1} 名：{lotInfo?.title || lot.title}
                      </div>
                      {lotInfo?.interpretation && (
                        <div className="text-xs text-amber-600 italic">
                          {lotInfo.interpretation}
                        </div>
                      )}
                    </div>
                    <div className="px-2 py-1 bg-amber-100 rounded text-xs font-bold text-amber-700">
                      {lot.chips} 筹码
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Phase 1: TA的Top3揭晓 */}
      {revealPhase >= 1 && (
        <div className="mb-6 animate-fade-in">
          <div className="bg-white rounded-xl p-4 border-2 border-blue-300 shadow-md">
            <div className="text-center mb-3">
              <div className="text-sm font-bold text-blue-800 mb-2">TA 的 Top3</div>
            </div>
            <div className="space-y-2">
              {partnerUser.top3.map((lot, i) => {
                const lotInfo = getLotInfo(lot.lot_id)
                return (
                  <div
                    key={lot.lot_id}
                    className="flex items-center gap-3 p-2 rounded-lg border transition-all hover:shadow-md"
                    style={{
                      borderColor: lotInfo?.theme_color || '#3B82F6',
                      animationDelay: `${i * 0.2}s`
                    }}
                  >
                    <div className="text-2xl">{lotInfo?.icon || '💰'}</div>
                    <div className="flex-1">
                      <div className="text-sm font-bold text-blue-900">
                        第 {i + 1} 名：{lotInfo?.title || lot.title}
                      </div>
                      {lotInfo?.interpretation && (
                        <div className="text-xs text-blue-600 italic">
                          {lotInfo.interpretation}
                        </div>
                      )}
                    </div>
                    <div className="px-2 py-1 bg-blue-100 rounded text-xs font-bold text-blue-700">
                      {lot.chips} 筹码
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Phase 2: 共鸣拍品揭晓 */}
      {revealPhase >= 2 && resonantLots.length > 0 && (
        <div className="mb-6 animate-fade-in">
          <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl p-4 border-2 border-green-300 shadow-md">
            <div className="text-center mb-3">
              <div className="text-lg mb-2">💫</div>
              <div className="text-sm font-bold text-green-800 mb-2">共鸣拍品</div>
              <div className="text-xs text-green-600">你们都看重的人生</div>
            </div>
            <div className="space-y-2">
              {resonantLots.map((lot, i) => (
                <div
                  key={lot.lot_id}
                  className="flex items-center gap-3 p-2 bg-white rounded-lg border border-green-200"
                >
                  <div className="text-2xl">{lot.icon}</div>
                  <div className="flex-1 text-sm font-medium text-green-900">
                    {lot.title}
                  </div>
                  <div className="flex gap-2 text-xs">
                    <div className="px-2 py-1 bg-amber-100 rounded text-amber-700">
                      你: {lot.user1_chips}
                    </div>
                    <div className="px-2 py-1 bg-blue-100 rounded text-blue-700">
                      TA: {lot.user2_chips}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Phase 3: 分歧拍品揭晓 */}
      {revealPhase >= 3 && divergentLots.length > 0 && (
        <div className="mb-6 animate-fade-in">
          <div className="bg-gradient-to-r from-orange-50 to-yellow-50 rounded-xl p-4 border-2 border-orange-300 shadow-md">
            <div className="text-center mb-3">
              <div className="text-lg mb-2">⚡</div>
              <div className="text-sm font-bold text-orange-800 mb-2">分歧拍品</div>
              <div className="text-xs text-orange-600">你们看重程度不同的人生</div>
            </div>
            <div className="space-y-2">
              {divergentLots.map((lot, i) => (
                <div
                  key={lot.lot_id}
                  className="flex items-center gap-3 p-2 bg-white rounded-lg border border-orange-200"
                >
                  <div className="text-2xl">{lot.icon}</div>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-orange-900">
                      {lot.title}
                    </div>
                    <div className="text-xs text-orange-600">
                      {lot.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Phase 4: 冲突风险揭晓 */}
      {revealPhase >= 4 && conflicts.length > 0 && (
        <div className="mb-6 animate-fade-in">
          <div className="bg-gradient-to-r from-red-50 to-pink-50 rounded-xl p-4 border-2 border-red-300 shadow-md">
            <div className="text-center mb-3">
              <div className="text-lg mb-2">⚠️</div>
              <div className="text-sm font-bold text-red-800 mb-2">冲突风险</div>
              <div className="text-xs text-red-600">需要注意的价值观冲突</div>
            </div>
            <div className="space-y-3">
              {conflicts.map((conflict, i) => (
                <div
                  key={i}
                  className="bg-white rounded-lg p-3 border border-red-200"
                >
                  <div className="text-sm font-medium text-red-900 mb-1">
                    {conflict.type}
                  </div>
                  <div className="text-xs text-red-700 mb-2">
                    {conflict.description}
                  </div>
                  <div className="text-xs text-red-600 italic font-medium">
                    💡 建议：{conflict.suggestion}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 整体契合度 */}
      <div className={`text-center mb-6 p-4 rounded-xl ${matchColor.bg} animate-fade-in`}>
        <div className={`text-lg font-bold ${matchColor.text}`}>{match_type}</div>
      </div>

      {/* 继续按钮 */}
      {onContinue && revealPhase >= 4 && (
        <button
          onClick={onContinue}
          className="w-full py-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white font-medium rounded-xl shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] transition-all"
        >
          查看详细建议
        </button>
      )}
    </div>
  )
}

// ============================================================
// 辅助函数
// ============================================================

function getMatchColor(matchType: string) {
  if (matchType.includes('高度')) {
    return { bg: 'bg-green-50', text: 'text-green-700' }
  } else if (matchType.includes('中等')) {
    return { bg: 'bg-yellow-50', text: 'text-yellow-700' }
  } else if (matchType.includes('磨合') || matchType.includes('冲突')) {
    return { bg: 'bg-red-50', text: 'text-red-700' }
  } else {
    return { bg: 'bg-amber-50', text: 'text-amber-700' }
  }
}