'use client'

import Image from 'next/image'
import { BadgeCheck, ChevronRight, MapPin } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'
import type { CandidatePreview } from '@/lib/types/candidate'

type DiscoveryCandidateCardProps = {
  candidate: CandidatePreview
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  className?: string
  style?: React.CSSProperties
}

export function DiscoveryCandidateCard({
  candidate,
  onViewCandidate,
  className,
  style,
}: DiscoveryCandidateCardProps) {
  const imageSrc = resolveProfileImageUrl(candidate.image, PLACEHOLDER_AVATAR)
  const mbtiType = candidate.personality_match_context?.mbti?.type_code
  const attachmentType = candidate.personality_match_context?.attachment?.type_code

  return (
    <button
      type="button"
      onClick={() => onViewCandidate(candidate.id, candidate)}
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
            unoptimized={imageSrc.startsWith('data:image/')}
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
          </div>
          {candidate.matchReason ? (
            <p className="text-xs text-primary mt-2 line-clamp-2">
              <span className="text-muted-foreground">匹配点：</span>
              {candidate.matchReason}
            </p>
          ) : null}

          {/* ===== Phase 1: 测评推荐理由展示 ===== */}
          {candidate.personality_reasons && candidate.personality_reasons.length > 0 ? (
            <div className="mt-2">
              <p className="text-xs text-muted-foreground mb-1">从测评角度看：</p>
              <div className="flex flex-wrap gap-1">
                {candidate.personality_reasons.slice(0, 2).map((reason, idx) => (
                  <span
                    key={idx}
                    className="inline-block px-2 py-0.5 text-xs bg-primary/10 text-primary rounded border border-primary/20"
                  >
                    {reason}
                  </span>
                ))}
              </div>
            </div>
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
