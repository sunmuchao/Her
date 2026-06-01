'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

export function AssessmentResultCard({
  data,
  onAddLabels,
}: {
  data: {
    type_code: string
    scores: Record<string, number>
    dimension_rows: Array<{
      key: string
      name: string
      score: number
      level: 'high' | 'medium' | 'low'
      trait: string
    }>
    labels: string[]
    interpretation_data?: {
      summary: string
      love_style: string
      match_suggestions: string[]
      extreme_tags?: Array<{
        tag: string
        description: string
      }>
    }
    reward: string
    assessment_id: string
  }
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
}) {
  // 标签勾选状态：默认选中昵称（第一个标签）
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(new Set([data.labels[0]]))
  const [isAdding, setIsAdding] = useState(false)
  const [added, setAdded] = useState(false)

  const toggleLabel = (label: string) => {
    const newSelected = new Set(selectedLabels)
    if (newSelected.has(label)) {
      newSelected.delete(label)
    } else {
      newSelected.add(label)
    }
    setSelectedLabels(newSelected)
  }

  const handleAddLabels = async () => {
    if (!onAddLabels || selectedLabels.size === 0) return
    setIsAdding(true)
    try {
      await onAddLabels(Array.from(selectedLabels))
      setAdded(true)
    } finally {
      setIsAdding(false)
    }
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-sm">
      <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">测评结果</div>
      <div className="mt-2 text-2xl font-semibold">{data.type_code}</div>

      {/* 极端标签（高亮显示） */}
      {data.interpretation_data?.extreme_tags?.length > 0 && (
        <div className="mt-3 space-y-2">
          {data.interpretation_data.extreme_tags.map((extreme, idx) => (
            <div
              key={idx}
              className="rounded-full bg-gradient-to-r from-pink-100 to-yellow-100 px-3 py-2 text-sm border border-pink-200"
            >
              <span className="font-medium text-pink-700">🌟 {extreme.tag}</span>
              <span className="ml-2 text-pink-600 text-xs">{extreme.description}</span>
            </div>
          ))}
        </div>
      )}

      {/* 标签勾选区域 */}
      <div className="mt-3">
        <div className="text-xs text-muted-foreground mb-2">你的恋爱标签（点击勾选想要的）：</div>
        <div className="flex flex-wrap gap-2">
          {data.labels.map((label) => (
            <label
              key={label}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs cursor-pointer transition-colors ${
                selectedLabels.has(label)
                  ? 'bg-primary/20 border border-primary/40'
                  : 'bg-secondary border border-transparent'
              }`}
              onClick={() => toggleLabel(label)}
            >
              <Checkbox
                checked={selectedLabels.has(label)}
                onCheckedChange={() => toggleLabel(label)}
                className="h-3.5 w-3.5"
              />
              <span>{label}</span>
            </label>
          ))}
        </div>

        {/* 添加按钮 */}
        {onAddLabels && !added && (
          <Button
            variant="outline"
            size="sm"
            className="mt-3 w-full"
            disabled={selectedLabels.size === 0 || isAdding}
            onClick={handleAddLabels}
          >
            {isAdding ? '添加中...' : `添加 ${selectedLabels.size} 个标签到我的页面`}
          </Button>
        )}
        {added && (
          <div className="mt-3 text-xs text-center text-muted-foreground">✅ 已添加到个人标签</div>
        )}
      </div>

      {/* 维度得分 */}
      <div className="mt-4 grid gap-3">
        {data.dimension_rows.map((row) => (
          <div key={row.key}>
            <div className="mb-1 flex justify-between text-sm">
              <span>{row.name}</span>
              <span>{row.score.toFixed(1)}</span>
            </div>
            <div className="h-2 rounded-full bg-secondary">
              <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${row.score}%` }} />
            </div>
          </div>
        ))}
      </div>

      <p className="mt-4 text-sm text-muted-foreground">{data.reward}</p>

      {/* AI 解读（暂时保留，后续改成小雅对话） */}
      {data.interpretation_data ? (
        <div className="mt-5 rounded-2xl bg-secondary/40 p-4">
          <div className="text-xs uppercase tracking-[0.24em] text-muted-foreground">AI 解读</div>
          <p className="mt-3 text-sm leading-relaxed">{data.interpretation_data.summary}</p>
          <p className="mt-3 text-sm text-muted-foreground">{data.interpretation_data.love_style}</p>
          <div className="mt-4 space-y-2">
            {data.interpretation_data.match_suggestions.map((item) => (
              <div key={item} className="rounded-2xl bg-background px-3 py-2 text-sm">
                {item}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}