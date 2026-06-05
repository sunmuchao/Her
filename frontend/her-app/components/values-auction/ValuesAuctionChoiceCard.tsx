/**
 * 价值观拍卖会复用/重做选择卡片
 *
 * 用户之前做过拍卖，点"一起做"后弹出此选择。
 */

import React, { useState } from 'react'

type LastResult = {
  value_type: string
  top3: Array<{ lot_id: string; title: string; chips: number }>
}

type Props = {
  lastResult: LastResult
  onReuse: () => void
  onRedo: () => void
}

export function ValuesAuctionChoiceCard({ lastResult, onReuse, onRedo }: Props) {
  const [choice, setChoice] = useState<'reuse' | 'redo'>('reuse')

  const handleConfirm = () => {
    if (choice === 'reuse') {
      onReuse()
    } else {
      onRedo()
    }
  }

  return (
    <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 shadow-lg border border-amber-200 animate-fade-in">
      {/* 标题 */}
      <div className="text-center mb-6">
        <div className="text-4xl mb-2 animate-scale-in">
          📋
        </div>
        <h2 className="text-xl font-bold text-amber-900">你之前做过价值观拍卖</h2>
        <p className="text-amber-600 mt-2 text-sm">选择使用上次结果，还是重新做一遍</p>
      </div>

      {/* 选择选项 */}
      <div className="space-y-3 mb-6">
        {/* 复用上次结果 */}
        <div
          onClick={() => setChoice('reuse')}
          className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
            choice === 'reuse'
              ? 'bg-amber-100 border-amber-400 shadow-md'
              : 'bg-white border-gray-200 hover:border-amber-200'
          }`}
        >
          <div className="flex items-center gap-3">
            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
              choice === 'reuse' ? 'border-amber-500 bg-amber-500' : 'border-gray-300'
            }`}>
              {choice === 'reuse' && (
                <div className="w-2 h-2 bg-white rounded-full animate-scale-in" />
              )}
            </div>
            <div>
              <div className="font-medium text-amber-900">复用上次结果</div>
              <div className="text-xs text-amber-600 mt-1">
                直接使用之前的选择，快速完成
              </div>
            </div>
          </div>

          {/* 上次结果预览 */}
          {choice === 'reuse' && (
            <div className="mt-3 pl-8 animate-fade-in">
              <div className="bg-amber-50 rounded-lg p-3">
                <div className="text-sm text-amber-700 font-medium mb-2">
                  {lastResult.value_type}
                </div>
                <div className="flex gap-2 text-xs">
                  {lastResult.top3.map((trait, i) => (
                    <span key={i} className="px-2 py-1 bg-amber-100 rounded-full text-amber-600">
                      {trait.title} {trait.chips}票
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 重新做一遍 */}
        <div
          onClick={() => setChoice('redo')}
          className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${
            choice === 'redo'
              ? 'bg-orange-100 border-orange-400 shadow-md'
              : 'bg-white border-gray-200 hover:border-orange-200'
          }`}
        >
          <div className="flex items-center gap-3">
            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
              choice === 'redo' ? 'border-orange-500 bg-orange-500' : 'border-gray-300'
            }`}>
              {choice === 'redo' && (
                <div className="w-2 h-2 bg-white rounded-full animate-scale-in" />
              )}
            </div>
            <div>
              <div className="font-medium text-orange-900">重新做一遍</div>
              <div className="text-xs text-orange-600 mt-1">
                可能你的想法变了，重新测一下
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 确认按钮 */}
      <button
        onClick={handleConfirm}
        className={`w-full py-3 font-medium rounded-xl shadow-md transition-all hover:scale-[1.02] active:scale-[0.98] ${
          choice === 'reuse'
            ? 'bg-gradient-to-r from-amber-500 to-orange-500 text-white'
            : 'bg-gradient-to-r from-orange-500 to-red-500 text-white'
        }`}
      >
        {choice === 'reuse' ? '使用上次结果' : '重新拍卖'}
      </button>
    </div>
  )
}
