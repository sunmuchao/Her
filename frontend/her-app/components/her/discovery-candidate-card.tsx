'use client'

import { useEffect, useRef } from 'react'
import Image from 'next/image'
import { BadgeCheck, ChevronRight, MapPin } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl, shouldBypassNextImageOptimization } from '@/lib/image-url'
import { recordDiscoveryCandidateTelemetry } from '@/lib/api/endpoints/discovery'
import type { CandidatePreview } from '@/lib/types/candidate'

type DiscoveryCandidateCardProps = {
  candidate: CandidatePreview
  sessionId?: string | null
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null) => void
  className?: string
  style?: React.CSSProperties
}

export function DiscoveryCandidateCard({
  candidate,
  sessionId,
  onViewCandidate,
  className,
  style,
}: DiscoveryCandidateCardProps) {
  const imageSrc = resolveProfileImageUrl(candidate.image, PLACEHOLDER_AVATAR)
  const imageUnoptimized = shouldBypassNextImageOptimization(imageSrc)
  const subtitleParts = String(candidate.subtitle || '')
    .split('·')
    .map((part) => part.trim())
    .filter(Boolean)
  const primaryMeta = [candidate.city, candidate.occupation || candidate.education].filter(Boolean)
  const secondaryMeta = subtitleParts.filter(
    (part) => part && !primaryMeta.includes(part),
  )
  const mbtiType = candidate.personality_match_context?.mbti?.type_code
  const attachmentType = candidate.personality_match_context?.attachment?.type_code
  const matchHighlights = (candidate.matchHighlights || []).filter(Boolean).slice(0, 4)
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const hasRecordedImpressionRef = useRef(false)
  const visibleStartRef = useRef<number | null>(null)

  useEffect(() => {
    const numericCandidateId = Number(candidate.id)
    if (!sessionId || !buttonRef.current || !Number.isFinite(numericCandidateId) || numericCandidateId <= 0) {
      return
    }
    const node = buttonRef.current
    const flushVisibleDuration = () => {
      const startedAt = visibleStartRef.current
      if (!startedAt) return
      visibleStartRef.current = null
      const durationMs = Math.max(0, Math.round(performance.now() - startedAt))
      if (durationMs < 250) return
      void recordDiscoveryCandidateTelemetry({
        sessionId,
        candidateId: numericCandidateId,
        telemetry: {
          card_visible_duration_ms: durationMs,
        },
      }).catch(() => {})
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return
        if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
          if (!hasRecordedImpressionRef.current) {
            hasRecordedImpressionRef.current = true
            void recordDiscoveryCandidateTelemetry({
              sessionId,
              candidateId: numericCandidateId,
              telemetry: {
                card_impression_count: 1,
              },
            }).catch(() => {})
          }
          if (!visibleStartRef.current) {
            visibleStartRef.current = performance.now()
          }
          return
        }
        flushVisibleDuration()
      },
      { threshold: [0, 0.6, 1] },
    )
    observer.observe(node)
    return () => {
      observer.disconnect()
      flushVisibleDuration()
    }
  }, [candidate.id, sessionId])

  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={() => onViewCandidate(candidate.id, candidate, sessionId)}
      className={cn(
        'w-full bg-card border border-border rounded-xl p-3 text-left transition-all',
        'hover:border-primary/30 hover:shadow-sm',
        'focus-ring',
        className,
      )}
      style={style}
      aria-label={`查看候选人 ${candidate.name} 的详细资料`}
    >
      <div className="flex gap-3">
        <div className="relative w-16 h-20 rounded-lg overflow-hidden shrink-0 bg-secondary">
          <Image
            src={imageSrc}
            alt={candidate.name}
            fill
            className="object-cover"
            sizes="64px"
            loading="lazy"
            unoptimized={imageUnoptimized}
          />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground">{candidate.name}</span>
            {candidate.age ? (
              <span className="text-sm text-muted-foreground">{candidate.age}岁</span>
            ) : null}
            {candidate.verified ? (
              <BadgeCheck className="w-4 h-4 text-primary" aria-label="已认证" />
            ) : null}
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            {candidate.city ? (
              <span className="flex items-center gap-1">
                <MapPin className="w-3 h-3" aria-hidden="true" />
                {candidate.city}
              </span>
            ) : null}
            {candidate.occupation ? <span>{candidate.occupation}</span> : null}
            {!candidate.occupation && candidate.education ? <span>{candidate.education}</span> : null}
          </div>
          {!candidate.occupation && secondaryMeta.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-1">
              {secondaryMeta.join(' · ')}
            </p>
          ) : null}
          {matchHighlights.length > 0 ? (
            <div className="mt-2">
              <p className="text-xs text-muted-foreground mb-1">匹配点：</p>
              <div className="flex flex-wrap gap-1">
                {matchHighlights.map((item, idx) => (
                  <span
                    key={`${candidate.id}-highlight-${idx}`}
                    className="inline-block px-2 py-0.5 text-xs bg-primary/10 text-primary rounded border border-primary/20"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ) : candidate.matchReason ? (
            <p className="text-xs text-primary mt-2 line-clamp-2">
              <span className="text-muted-foreground">匹配点：</span>
              {candidate.matchReason}
            </p>
          ) : null}

          {/* ===== Phase 1: 测评结果展示（原始显示） ===== */}
          {candidate.personality_match_context?.availability ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {candidate.personality_match_context.availability.has_mbti && mbtiType ? (
                <span className="inline-block px-2 py-0.5 text-xs bg-green-50 text-green-600 rounded border border-green-200">
                  MBTI: {mbtiType}
                </span>
              ) : null}
              {candidate.personality_match_context.availability.has_attachment && attachmentType ? (
                <span className="inline-block px-2 py-0.5 text-xs bg-blue-50 text-blue-600 rounded border border-blue-200">
                  依恋: {attachmentType === 'secure' ? '安全型' :
                         attachmentType === 'anxious' ? '焦虑型' :
                         attachmentType === 'avoidant' ? '回避型' :
                         attachmentType === 'fearful' ? '恐惧型' : attachmentType}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="flex flex-col items-end justify-center">
          <ChevronRight className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
        </div>
      </div>
    </button>
  )
}
