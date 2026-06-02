'use client'

import { useState, useMemo, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Share2, Check, Star, Trophy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { type AssessmentType } from './assessment-themes'
import { ConfettiCelebration, AnimatedNumber } from './immersive-effects'

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

// Attachment style type nicknames
const ATTACHMENT_NICKNAMES: Record<string, string> = {
  secure: '安全型',
  anxious: '焦虑型',
  avoidant: '回避型',
  fearful: '恐惧型',
}

// Love language type nicknames
const LOVE_LANGUAGE_NICKNAMES: Record<string, string> = {
  words_of_affirmation: '肯定言词',
  quality_time: '精心时刻',
  receiving_gifts: '接受礼物',
  acts_of_service: '服务行动',
  physical_touch: '身体接触',
  // 兼容可能的简写形式
  words: '肯定言词',
  time: '精心时刻',
  gifts: '接受礼物',
  service: '服务行动',
  touch: '身体接触',
}

function normalizeTypeCode(typeCode?: string) {
  return typeCode?.trim().toLowerCase()
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
  type_code?: string
  scores: Record<string, number>
  dimension_rows?: DimensionRow[]
  labels?: string[]  // 改为可选，因为后端可能不返回
  interpretation_data?: InterpretationData
  reward: string
  assessment_id: string
}

// Dimension label mapping with explanations (matching backend keys)
const DIMENSION_LABELS: Record<string, { high: string; low: string }> = {
  // MBTI dimensions
  'ei': { high: '外向', low: '内向' },
  'sn': { high: '直觉', low: '感觉' },
  'tf': { high: '思考', low: '情感' },
  'jp': { high: '判断', low: '感知' },
  // Love language dimensions (雷达图高低标签)
  'words_of_affirmation': { high: '肯定言词敏感', low: '肯定言词不敏感' },
  'quality_time': { high: '精心时刻敏感', low: '精心时刻不敏感' },
  'receiving_gifts': { high: '接受礼物敏感', low: '接受礼物不敏感' },
  'acts_of_service': { high: '服务行动敏感', low: '服务行动不敏感' },
  'physical_touch': { high: '身体接触敏感', low: '身体接触不敏感' },
  // Attachment dimensions (雷达图高低标签)
  'secure': { high: '安全感强', low: '安全感弱' },
  'anxious': { high: '焦虑度高', low: '焦虑度低' },
  'avoidant': { high: '回避度高', low: '回避度低' },
  'fearful': { high: '恐惧度高', low: '恐惧度低' },
}

// Radar Chart Component
function RadarChart({
  dimensions = [],
  size = 280,
  assessmentType,
}: {
  dimensions?: DimensionRow[]
  size?: number
  assessmentType?: AssessmentType
}) {
  const center = size / 2
  const maxRadius = (size / 2) - 50
  const levels = 4

  // Get theme color for the chart
  const chartColorClass = assessmentType === 'attachment_style' 
    ? 'text-coral' 
    : assessmentType === 'love_language' 
      ? 'text-lavender' 
      : 'text-primary'

  if (!dimensions.length) {
    return (
      <div className="flex h-[280px] items-center justify-center rounded-3xl border border-dashed border-border text-sm text-muted-foreground">
        {"暂无雷达图数据"}
      </div>
    )
  }

  // Calculate points for each dimension (memoized)
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
  const polygonPath = useMemo(() => {
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ') + ' Z'
  }, [points])

  // Calculate label positions based on actual SVG coordinates (memoized with collision detection)
  const labelPositions = useMemo(() => {
    const positions = dimensions.map((dim, i) => {
      const angle = (Math.PI * 2 * i) / dimensions.length - Math.PI / 2
      const labelRadius = maxRadius + 35
      const x = center + Math.cos(angle) * labelRadius
      const y = center + Math.sin(angle) * labelRadius
      return { x, y, angle, key: dim.key }
    })
    
    // Simple collision detection and adjustment
    const minDistance = 40
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[j].x - positions[i].x
        const dy = positions[j].y - positions[i].y
        const distance = Math.sqrt(dx * dx + dy * dy)
        
        if (distance < minDistance) {
          // Push labels apart slightly
          const adjustment = (minDistance - distance) / 2
          const angle = Math.atan2(dy, dx)
          positions[i].x -= Math.cos(angle) * adjustment
          positions[i].y -= Math.sin(angle) * adjustment
          positions[j].x += Math.cos(angle) * adjustment
          positions[j].y += Math.sin(angle) * adjustment
        }
      }
    }
    
    return positions
  }, [dimensions, center, maxRadius])

  return (
    <div className="relative will-change-transform" style={{ width: size, height: size }}>
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
          className={chartColorClass}
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r="4"
            fill="currentColor"
            className={chartColorClass}
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
            <div className="text-xs font-medium text-foreground mb-0.5 text-center leading-tight">
              {dim.name}
            </div>
            <div className="text-[10px] text-muted-foreground text-center leading-tight">
              {isHigh ? dimLabel.high : dimLabel.low}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function getTypeNickname(typeCode?: string, assessmentType?: AssessmentType): string {
  if (!typeCode) {
    return ''
  }

  const normalizedTypeCode = normalizeTypeCode(typeCode)
  if (assessmentType === 'attachment_style') {
    return ATTACHMENT_NICKNAMES[normalizedTypeCode || ''] || ''
  }
  if (assessmentType === 'love_language') {
    return LOVE_LANGUAGE_NICKNAMES[normalizedTypeCode || ''] || ''
  }
  return TYPE_NICKNAMES[typeCode.trim()] || ''
}

export function AssessmentResultCard({
  data,
  onAddLabels,
  onShare,
  assessmentType,
}: {
  data: ResultData
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
  onShare?: () => void
  assessmentType?: AssessmentType
}) {
  const [isAdding, setIsAdding] = useState(false)
  const [addedLabels, setAddedLabels] = useState<Set<string>>(new Set())
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    label: string
  }>({ open: false, label: '' })
  const [showConfetti, setShowConfetti] = useState(false)
  const [isRevealed, setIsRevealed] = useState(false)
  
  // Trigger confetti and reveal animation on mount
  useEffect(() => {
    const confettiTimer = setTimeout(() => setShowConfetti(true), 300)
    const revealTimer = setTimeout(() => setIsRevealed(true), 100)
    return () => {
      clearTimeout(confettiTimer)
      clearTimeout(revealTimer)
    }
  }, [])

  // 对于恋爱语言测评，优先显示中文昵称而不是英文 type_code
  const typeNickname = getTypeNickname(data.type_code, assessmentType)
  const rawTypeCode = data.type_code?.trim()
  const safeTypeCode = assessmentType === 'love_language'
    ? (typeNickname || rawTypeCode || '--')
    : (rawTypeCode || '--')

  // Theme-based colors
  const extremeTagBg = assessmentType === 'attachment_style' 
    ? 'bg-coral-soft/60 border-coral/20' 
    : assessmentType === 'love_language' 
      ? 'bg-lavender-soft/60 border-lavender/20' 
      : 'bg-rose-soft/60 border-rose/20'
  
  const extremeTagIcon = assessmentType === 'attachment_style' 
    ? 'text-coral' 
    : assessmentType === 'love_language' 
      ? 'text-lavender' 
      : 'text-rose'

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

  // Selected label colors
  const selectedLabelClass = assessmentType === 'attachment_style' 
    ? 'bg-coral/15 border-coral/40' 
    : assessmentType === 'love_language' 
      ? 'bg-lavender/15 border-lavender/40' 
      : 'bg-primary/15 border-primary/40'

  return (
    <>
      {/* Confetti celebration */}
      <ConfettiCelebration 
        trigger={showConfetti} 
        colors={
          assessmentType === 'attachment_style' 
            ? ['var(--coral)', 'var(--rose)', 'var(--gold)']
            : assessmentType === 'love_language'
              ? ['var(--lavender)', 'var(--purple)', 'var(--rose)']
              : undefined
        }
        pieceCount={40}
      />
      
      <div className={cn(
        'rounded-3xl border border-border bg-card p-6 shadow-sm overflow-y-auto max-h-[70vh] scroll-fade-bottom',
        isRevealed ? 'animate-score-reveal' : 'opacity-0 scale-90'
      )}>
        {/* Trophy icon */}
        <div className="flex justify-center mb-4">
          <div className={cn(
            'w-16 h-16 rounded-full flex items-center justify-center',
            assessmentType === 'attachment_style' ? 'bg-coral/15' : 
            assessmentType === 'love_language' ? 'bg-lavender/15' : 'bg-primary/15'
          )}>
            <Trophy className={cn(
              'w-8 h-8',
              assessmentType === 'attachment_style' ? 'text-coral' : 
              assessmentType === 'love_language' ? 'text-lavender' : 'text-primary'
            )} />
          </div>
        </div>
        
        {/* Header with share button */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1 text-center">
            <div className={cn(
              'text-xs uppercase tracking-widest mb-2',
              assessmentType === 'attachment_style' ? 'text-coral' : 
              assessmentType === 'love_language' ? 'text-lavender' : 'text-muted-foreground'
            )}>
              {"测评结果"}
            </div>
            <div className="flex items-baseline justify-center gap-2">
              <span className={cn(
                'text-4xl font-bold tracking-tight animate-number-roll',
                assessmentType === 'attachment_style' ? 'text-coral' : 
                assessmentType === 'love_language' ? 'text-lavender' : ''
              )}>
                {safeTypeCode}
              </span>
            </div>
            {typeNickname && typeNickname !== safeTypeCode && (
              <div className="text-sm text-muted-foreground mt-1">{typeNickname}</div>
            )}
          </div>
        </div>
        
        {/* Share button */}
        {onShare && (
          <div className="flex justify-center mb-4">
            <button
              onClick={onShare}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-full text-sm transition-all touch-target active:scale-95',
                assessmentType === 'attachment_style' ? 'bg-coral/10 text-coral hover:bg-coral/20' : 
                assessmentType === 'love_language' ? 'bg-lavender/10 text-lavender hover:bg-lavender/20' : 
                'bg-secondary text-muted-foreground hover:bg-secondary/80'
              )}
            >
              <Share2 className="w-4 h-4" />
              {"分享结果"}
            </button>
          </div>
        )}

      {/* Extreme Tags */}
      {data.interpretation_data?.extreme_tags && data.interpretation_data.extreme_tags.length > 0 && (
        <div className="mb-5 space-y-2">
          {data.interpretation_data.extreme_tags.map((extreme, idx) => (
            <div
              key={idx}
              className={cn(
                'flex items-center gap-2 rounded-2xl border px-4 py-2.5',
                extremeTagBg
              )}
            >
              <Star className={cn('w-4 h-4 shrink-0', extremeTagIcon)} fill="currentColor" />
              <div>
                <span className={cn('font-medium text-sm', extremeTagIcon)}>{extreme.tag}</span>
                <span className="ml-2 text-xs text-muted-foreground">{extreme.description}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Radar Chart */}
      <div className="my-6 relative">
        <RadarChart 
          dimensions={data.dimension_rows} 
          size={280} 
          assessmentType={assessmentType}
        />
      </div>

      {/* Labels Selection */}
      <div className="mb-5">
        <div className="text-xs text-muted-foreground mb-2.5">
          {"你的恋爱标签（点击添加到我的主页）："}
        </div>
        <div className="flex flex-wrap gap-2">
          {(data.labels || []).map((label) => (
            <button
              key={label}
              onClick={() => handleLabelClick(label)}
              disabled={addedLabels.has(label) || isAdding}
              className={cn(
                'rounded-full px-3 py-1.5 text-xs cursor-pointer transition-all touch-target active:scale-95',
                addedLabels.has(label)
                  ? cn(selectedLabelClass, 'border text-foreground')
                  : 'bg-secondary border border-transparent text-muted-foreground hover:bg-secondary/80 hover:border-border',
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
          {(data.labels || []).length === 0 && (
            <div className="text-xs text-muted-foreground italic">
              {"暂无标签数据"}
            </div>
          )}
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
    </>
  )
}
