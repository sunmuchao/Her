'use client'

import { CheckCircle, XCircle, AlertTriangle, Clock, User } from 'lucide-react'
import { FadeIn } from '@/components/her/ui/animations'
import type { VerificationReview } from '@/lib/api/endpoints/field-verification'

type ReviewHistoryListProps = {
  reviews: VerificationReview[]
}

function ReviewDecisionBadge({ decision }: { decision: string }) {
  const config: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
    approve: {
      label: '通过',
      icon: <CheckCircle className="w-3.5 h-3.5" />,
      className: 'bg-green-500/10 text-green-600 border-green-500/30',
    },
    reject: {
      label: '驳回',
      icon: <XCircle className="w-3.5 h-3.5" />,
      className: 'bg-rose/10 text-rose border-rose/30',
    },
    request_resubmission: {
      label: '补件',
      icon: <AlertTriangle className="w-3.5 h-3.5" />,
      className: 'bg-orange-500/10 text-orange-600 border-orange-500/30',
    },
  }

  const item = config[decision] || config.approve

  return (
    <span className={`px-2 py-1 rounded-lg text-xs border flex items-center gap-1 ${item.className}`}>
      {item.icon}
      {item.label}
    </span>
  )
}

function ReviewHistoryItem({ review, index }: { review: VerificationReview; index: number }) {
  const formatTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return timestamp
    }
  }

  const reviewedAt = review.reviewed_at || review.created_at || ''

  return (
    <FadeIn delay={index * 0.05}>
      <div className="rounded-xl bg-muted/30 p-3 border border-border/40">
        {/* 审核员和时间 */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <User className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">审核员 #{review.reviewer_id}</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">{formatTime(reviewedAt)}</span>
          </div>
        </div>

        {/* 审核决定 */}
        <div className="flex items-center gap-2 mb-2">
          <ReviewDecisionBadge decision={review.decision} />
          {review.decision === 'approve' && review.approved_value && (
            <span className="text-xs text-foreground">批准学历: {review.approved_value}</span>
          )}
        </div>

        {/* 审核备注 */}
        {review.review_note && (
          <div className="mt-2 pt-2 border-t border-border/30">
            <p className="text-xs text-muted-foreground">{review.review_note}</p>
          </div>
        )}

        {/* 补件清单 */}
        {review.decision === 'request_resubmission' && review.requested_documents && review.requested_documents.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border/30">
            <p className="text-xs text-muted-foreground mb-1">要求补充:</p>
            <div className="flex flex-wrap gap-1">
              {review.requested_documents.map((doc) => (
                <span key={doc} className="text-xs px-2 py-0.5 rounded bg-muted/40 text-foreground">
                  {doc}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </FadeIn>
  )
}

export default function ReviewHistoryList({ reviews }: ReviewHistoryListProps) {
  if (!reviews || reviews.length === 0) {
    return (
      <div className="text-sm text-muted-foreground text-center py-4">
        暂无审核历史记录
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-foreground">审核历史记录</p>
        <span className="text-xs text-muted-foreground">共 {reviews.length} 次</span>
      </div>

      <div className="space-y-2 max-h-[300px] overflow-y-auto">
        {reviews.map((review, index) => (
          <ReviewHistoryItem key={review.review_id} review={review} index={index} />
        ))}
      </div>
    </div>
  )
}