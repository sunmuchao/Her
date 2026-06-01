'use client'

import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Share2, Sparkles, Check, Star } from 'lucide-react'
import { cn } from '@/lib/utils'

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

// Radar Chart Component
function RadarChart({ dimensions, size = 200 }: { dimensions: DimensionRow[]; size?: number }) {
  const center = size / 2
  const maxRadius = (size / 2) - 30
  const levels = 4
  
  // Calculate points for each dimension
  const points = useMemo(() => {
    return dimensions.map((dim, i) => {
      const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
      const radius = (dim.score / 100) * maxRadius
      return {
        x: center + Math.cos(angle) * radius,
        y: center + Math.sin(angle) * radius,
        labelX: center + Math.cos(angle) * (maxRadius + 20),
        labelY: center + Math.sin(angle) * (maxRadius + 20),
        dim,
      }
    })
  }, [dimensions, center, maxRadius])
  
  // Create polygon path
  const polygonPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z'
  
  return (
    <svg width={size} height={size} className="mx-auto">
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
      
      {/* Labels */}
      {points.map((p, i) => (
        <text
          key={i}
          x={p.labelX}
          y={p.labelY}
          textAnchor="middle"
          dominantBaseline="middle"
          className="text-xs fill-muted-foreground"
        >
          {p.dim.key}
        </text>
      ))}
    </svg>
  )
}

// Dimension bar component
function DimensionBar({ row }: { row: DimensionRow }) {
  const levelColors = {
    high: 'bg-rose',
    medium: 'bg-gold',
    low: 'bg-taupe',
  }
  
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          <span className="font-medium">{row.name}</span>
          <span className="text-xs text-muted-foreground">({row.trait})</span>
        </span>
        <span className="tabular-nums">{row.score.toFixed(1)}</span>
      </div>
      <div className="h-2 rounded-full bg-secondary overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-700 ease-out',
            levelColors[row.level]
          )}
          style={{ width: `${row.score}%` }}
        />
      </div>
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
  const [selectedLabels, setSelectedLabels] = useState<Set<string>>(() => new Set([data.labels[0]]))
  const [isAdding, setIsAdding] = useState(false)
  const [added, setAdded] = useState(false)

  const typeNickname = TYPE_NICKNAMES[data.type_code] || ''

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
      <div className="my-6">
        <RadarChart dimensions={data.dimension_rows} size={180} />
      </div>

      {/* Labels Selection */}
      <div className="mb-5">
        <div className="text-xs text-muted-foreground mb-2.5">
          {"你的恋爱标签（点击选择想要展示的）："}
        </div>
        <div className="flex flex-wrap gap-2">
          {data.labels.map((label) => (
            <label
              key={label}
              className={cn(
                'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs cursor-pointer transition-all',
                selectedLabels.has(label)
                  ? 'bg-primary/15 border border-primary/40 text-foreground'
                  : 'bg-secondary border border-transparent text-muted-foreground hover:bg-secondary/80'
              )}
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

        {/* Add labels button */}
        {onAddLabels && !added && (
          <Button
            variant="outline"
            size="sm"
            className="mt-3 w-full"
            disabled={selectedLabels.size === 0 || isAdding}
            onClick={handleAddLabels}
          >
            {isAdding ? '添加中...' : `添加 ${selectedLabels.size} 个标签到我的主页`}
          </Button>
        )}
        {added && (
          <div className="mt-3 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <Check className="w-3.5 h-3.5 text-primary" />
            <span>{"已添加到个人标签"}</span>
          </div>
        )}
      </div>

      {/* Dimension Scores */}
      <div className="space-y-3 mb-5">
        <div className="text-xs text-muted-foreground">{"维度得分"}</div>
        {data.dimension_rows.map((row) => (
          <DimensionBar key={row.key} row={row} />
        ))}
      </div>

      {/* Reward */}
      <div className="flex items-center gap-2 rounded-2xl bg-gold-soft/50 border border-gold/20 px-4 py-3 mb-5">
        <Sparkles className="w-4 h-4 text-gold shrink-0" />
        <span className="text-sm">{data.reward}</span>
      </div>

      {/* AI Interpretation */}
      {data.interpretation_data && (
        <div className="rounded-2xl bg-secondary/40 p-4 space-y-3">
          <div className="text-xs uppercase tracking-widest text-muted-foreground">
            {"AI 解读"}
          </div>
          <p className="text-sm leading-relaxed">{data.interpretation_data.summary}</p>
          <p className="text-sm text-muted-foreground">{data.interpretation_data.love_style}</p>
          
          {data.interpretation_data.match_suggestions.length > 0 && (
            <div className="space-y-2 pt-2">
              <div className="text-xs text-muted-foreground">{"匹配建议"}</div>
              {data.interpretation_data.match_suggestions.map((item, idx) => (
                <div
                  key={idx}
                  className="rounded-xl bg-background px-3 py-2 text-sm"
                >
                  {item}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
