'use client'

import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Share2, Check, Star } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

// MBTI type nicknames
const TYPE_NICKNAMES: Record<string, string> = {
  INTJ: '策略家',
  INTP: '逻辑学家',
  ENTJ: '指挥官',
  ENTP: '辩论家',
  INFJ: '提倡者',
  INFP: '调停者',
  ENFJ: '主人公',
  ENFP: '竞选者',
  ISTJ: '物流师',
  ISFJ: '守卫者',
  ESTJ: '总经理',
  ESFJ: '执政官',
  ISTP: '鉴赏家',
  ISFP: '探险家',
  ESTP: '企业家',
  ESFP: '表演者',
}

interface DimensionRow {
  key: string
  name: string
  score: number
  level: 'high' | 'medium' | 'low'
  trait: string
}

interface ExtremeTag {
  tag: string
  description: string
}

interface InterpretationData {
  summary: string
  love_style: string
  match_suggestions: string[]
  extreme_tags?: ExtremeTag[]
}

interface ResultData {
  type_code: string
  scores: Record<string, number>
  dimension_rows: DimensionRow[]
  labels: string[]
  interpretation_data?: InterpretationData
  reward: string
  assessment_id: string
}

// Dimension label mapping with explanations (matching backend keys)
const DIMENSION_LABELS: Record<string, { high: string; low: string }> = {
  'ei': { high: '外向', low: '内向' },
  'sn': { high: '直觉', low: '感觉' },
  'tf': { high: '思考', low: '情感' },
  'jp': { high: '判断', low: '感知' },
}

// Radar Chart Component
function RadarChart({ dimensions, size = 280 }: { dimensions: DimensionRow[]; size?: number }) {
  const center = size / 2
  const maxRadius = (size / 2) - 50
  const levels = 4

  // Calculate points for each dimension
  const points = useMemo(() => {
    return dimensions.map((dim, i) => {
      const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
      const radius = (dim.score / 100) * maxRadius
      return {
        x: center + Math.cos(angle) * radius,
        y: center + Math.sin(angle) * radius,
        angle,
        dim,
      }
    })
  }, [dimensions, center, maxRadius])

  // Create polygon path
  const polygonPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z'

  // Calculate label positions based on actual SVG coordinates
  const labelPositions = dimensions.map((dim, i) => {
    const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
    const labelRadius = maxRadius + 35
    const x = center + Math.cos(angle) * labelRadius
    const y = center + Math.sin(angle) * labelRadius
    return { x, y, angle }
  })

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="absolute top-0 left-0">
        {/* Background grid circles */}
        {Array.from({ length: levels }).map((_, i) => {
          const r = ((i + 1) / levels) * maxRadius
          return (
            <circle
              key={i}
              cx={center}
              cy={center}
              r={r}
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-border"
              strokeDasharray={i < levels - 1 ? '2 4' : 'none'}
            />
          )
        })}

        {/* Axis lines */}
        {points.map((p, i) => {
          const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
          const endX = center + Math.cos(angle) * maxRadius
          const endY = center + Math.sin(angle) * maxRadius
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={endX}
              y2={endY}
              stroke="currentColor"
              strokeWidth="1"
              className="text-border"
            />
          )
        })}

        {/* Data polygon */}
        <path
          d={polygonPath}
          fill="currentColor"
          fillOpacity="0.15"
          stroke="currentColor"
          strokeWidth="2"
          className="text-primary"
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="4"
            fill="currentColor"
            className="text-primary"
          />
        ))}

        {/* Center point */}
        <circle
          cx={center}
          cy={center}
          r="3"
          fill="currentColor"
          className="text-muted-foreground"
        />
      </svg>

      {/* External dimension labels with explanations */}
      {dimensions.map((dim, i) => {
        const pos = labelPositions[i]
        const dimLabel = DIMENSION_LABELS[dim.key] || { high: dim.key, low: dim.key }
        const isHigh = dim.score >= 50

        return (
          <div
            key={i}
            className="absolute flex flex-col items-center justify-center"
            style={{
              left: pos.x,
              top: pos.y,
              transform: 'translate(-50%, -50%)',
              width: '70px',
            }}
          >
            <div className="text-xs font-medium text-foreground mb-0.5">
              {dim.name}
            </div>
            <div className="text-[10px] text-muted-foreground">
              {isHigh ? dimLabel.high : dimLabel.low}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function AssessmentResultCard({
  data,
  onAddLabels,
  onShare,
}: {
  data: ResultData
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
  onShare?: () => void
}) {
  const [isAdding, setIsAdding] = useState(false)
  const [addedLabels, setAddedLabels] = useState<Set<string>>(new Set())
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    label: string
  }>({ open: false, label: '' })

  const typeNickname = TYPE_NICKNAMES[data.type_code] || ''

  const handleLabelClick = (label: string) => {
    if (!onAddLabels || addedLabels.has(label) || isAdding) return
    // 打开确认对话框
    setConfirmDialog({ open: true, label })
  }

  const handleConfirmAddLabel = async () => {
    const label = confirmDialog.label
    if (!onAddLabels || addedLabels.has(label)) return

    setIsAdding(true)
    setConfirmDialog({ open: false, label: '' })
    try {
      await onAddLabels([label])
      setAddedLabels((prev) => new Set(prev).add(label))
    } finally {
      setIsAdding(false)
    }
  }

  const handleCancelAddLabel = () => {
    setConfirmDialog({ open: false, label: '' })
  }

  return (
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm animate-scale-in overflow-y-auto max-h-[70vh]">
      {/* Header with share button */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground mb-1">
            {"测评结果"}
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight">{data.type_code}</span>
            {typeNickname && (
              <span className="text-sm text-muted-foreground">{"- "}{typeNickname}</span>
            )}
          </div>
        </div>
        {onShare && (
          <Button variant="ghost" size="icon-sm" onClick={onShare} aria-label="分享结果">
            <Share2 className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* Extreme Tags */}
      {data.interpretation_data?.extreme_tags && data.interpretation_data.extreme_tags.length > 0 && (
        <div className="mb-5 space-y-2">
          {data.interpretation_data.extreme_tags.map((extreme, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 rounded-2xl bg-rose-soft/60 border border-rose/20 px-4 py-2.5"
            >
              <Star className="w-4 h-4 text-rose shrink-0" fill="currentColor" />
              <div>
                <span className="font-medium text-sm text-rose">{extreme.tag}</span>
                <span className="ml-2 text-xs text-muted-foreground">{extreme.description}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Radar Chart */}
      <div className="my-6 relative">
        <RadarChart dimensions={data.dimension_rows} size={280} />
      </div>

      {/* Labels Selection */}
      <div className="mb-5">
        <div className="text-xs text-muted-foreground mb-2.5">
          {"你的恋爱标签（点击添加到我的主页）："}
        </div>
        <div className="flex flex-wrap gap-2">
          {data.labels.map((label) => (
            <button
              key={label}
              onClick={() => handleLabelClick(label)}
              disabled={addedLabels.has(label) || isAdding}
              className={cn(
                'rounded-full px-3 py-1.5 text-xs cursor-pointer transition-all',
                addedLabels.has(label)
                  ? 'bg-primary/15 border border-primary/40 text-foreground'
                  : 'bg-secondary border border-transparent text-muted-foreground hover:bg-secondary/80 hover:border-primary/20',
                isAdding && 'opacity-60 cursor-wait'
              )}
            >
              {addedLabels.has(label) ? (
                <span className="flex items-center gap-1">
                  <Check className="w-3 h-3" />
                  {label}
                </span>
              ) : (
                label
              )}
            </button>
          ))}
        </div>

        </div>

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={confirmDialog.open}
        title="添加恋爱标签"
        message={`是否将「${confirmDialog.label}」添加为我的标签？`}
        confirmText="添加"
        cancelText="暂不添加"
        onConfirm={handleConfirmAddLabel}
        onCancel={handleCancelAddLabel}
      />
    </div>
  )
}
