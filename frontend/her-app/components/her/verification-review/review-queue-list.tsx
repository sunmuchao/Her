'use client'

import { useState } from 'react'
import { Clock, FileText, User, CheckSquare, Square, XCircle, CheckCircle } from 'lucide-react'
import { FadeIn } from '@/components/her/ui/animations'
import { cn } from '@/lib/utils'
import type { ReviewQueueItem } from '@/lib/api/endpoints/field-verification'

type ReviewQueueListProps = {
  submissions: ReviewQueueItem[]
  onItemClick: (submissionId: string) => void
  onBatchReview?: (submissionIds: string[], decision: 'approve' | 'reject') => void
}

function StatusBadge({ status }: { status: string }) {
  const statusConfig: Record<string, { label: string; className: string }> = {
    submitted: { label: '待审核', className: 'bg-gold/10 text-gold border-gold/30' },
    under_review: { label: '审核中', className: 'bg-primary/10 text-primary border-primary/30' },
    approved: { label: '已通过', className: 'bg-green-500/10 text-green-600 border-green-500/30' },
    rejected: { label: '已驳回', className: 'bg-rose/10 text-rose border-rose/30' },
    resubmission_required: { label: '需补件', className: 'bg-orange-500/10 text-orange-600 border-orange-500/30' },
  }

  const config = statusConfig[status] || statusConfig.submitted

  return (
    <span className={`px-2 py-1 rounded-lg text-xs border ${config.className}`}>{config.label}</span>
  )
}

function ReviewQueueItemCard({ submission, onClick, isSelected, onSelect }: {
  submission: ReviewQueueItem
  onClick: () => void
  isSelected: boolean
  onSelect: () => void
}) {
  const formatTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
      const diffDays = Math.floor(diffHours / 24)

      if (diffHours < 1) return '刚刚'
      if (diffHours < 24) return `${diffHours}小时前`
      if (diffDays < 7) return `${diffDays}天前`
      return date.toLocaleDateString('zh-CN')
    } catch {
      return timestamp
    }
  }

  const fieldKeyMap: Record<string, string> = {
    education: '学历认证',
    job: '职业认证',
    income: '收入认证',
  }

  const fieldLabel = fieldKeyMap[submission.field_key] || submission.field_key

  return (
    <FadeIn>
      <div
        className={cn(
          'w-full rounded-2xl border bg-card/70 p-4 transition-all relative',
          isSelected ? 'border-primary bg-primary/5' : 'border-border/60 hover:bg-card/90 hover:border-border/80',
        )}
      >
        {/* 复选框 */}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onSelect()
          }}
          className="absolute top-3 right-3 p-1 rounded hover:bg-muted/30 transition-colors"
        >
          {isSelected ? (
            <CheckSquare className="w-5 h-5 text-primary" />
          ) : (
            <Square className="w-5 h-5 text-muted-foreground" />
          )}
        </button>

        {/* 卡片内容 */}
        <button
          type="button"
          onClick={onClick}
          className="w-full text-left"
        >
          {/* 用户信息 */}
          <div className="flex items-start gap-3 mb-3 pr-8">
            <div className="w-10 h-10 rounded-full bg-muted/30 flex items-center justify-center">
              <User className="w-5 h-5 text-muted-foreground" />
            </div>
            <div className="flex-1">
              <p className="font-medium text-foreground">用户 #{submission.profile_id}</p>
              <p className="text-xs text-muted-foreground mt-1">{fieldLabel}</p>
            </div>
            <StatusBadge status={submission.status} />
          </div>

          {/* 申报值和时间 */}
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <FileText className="h-3.5 w-3.5" />
              <span>申报: {submission.declared_value || '—'}</span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              <span>{formatTime(submission.submitted_at || submission.created_at || '')}</span>
            </div>
          </div>

          {/* 审核次数 */}
          {submission.review_count && submission.review_count > 0 && (
            <div className="mt-2 text-xs text-muted-foreground">
              已审核 {submission.review_count} 次
            </div>
          )}
        </button>
      </div>
    </FadeIn>
  )
}

export default function ReviewQueueList({ submissions, onItemClick, onBatchReview }: ReviewQueueListProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // 选择/取消选择
  const toggleSelection = (submissionId: string) => {
    const newSet = new Set(selectedIds)
    if (newSet.has(submissionId)) {
      newSet.delete(submissionId)
    } else {
      newSet.add(submissionId)
    }
    setSelectedIds(newSet)
  }

  // 全选/取消全选
  const toggleAll = () => {
    if (selectedIds.size === submissions.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(submissions.map((s) => s.submission_id)))
    }
  }

  // 批量操作
  const handleBatchApprove = () => {
    if (onBatchReview && selectedIds.size > 0) {
      onBatchReview(Array.from(selectedIds), 'approve')
      setSelectedIds(new Set())
    }
  }

  const handleBatchReject = () => {
    if (onBatchReview && selectedIds.size > 0) {
      onBatchReview(Array.from(selectedIds), 'reject')
      setSelectedIds(new Set())
    }
  }

  const hasSelection = selectedIds.size > 0

  return (
    <>
      {/* 批量操作栏 */}
      {hasSelection && onBatchReview && (
        <div className="px-4 mb-3 sticky top-0 z-10">
          <div className="rounded-xl bg-primary/10 border border-primary/30 p-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckSquare className="w-4 h-4 text-primary" />
              <span className="text-sm text-primary">已选择 {selectedIds.size} 条</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleBatchApprove}
                className="rounded-lg bg-green-500/10 border border-green-500/30 px-3 py-1.5 text-sm text-green-600 hover:bg-green-500/20 transition-colors"
              >
                <CheckCircle className="w-3.5 h-3.5 inline mr-1" />
                批量通过
              </button>
              <button
                type="button"
                onClick={handleBatchReject}
                className="rounded-lg bg-rose/10 border border-rose/30 px-3 py-1.5 text-sm text-rose hover:bg-rose/20 transition-colors"
              >
                <XCircle className="w-3.5 h-3.5 inline mr-1" />
                批量驳回
              </button>
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted/30 transition-colors"
              >
                取消选择
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 全选按钮 */}
      {!hasSelection && submissions.length > 0 && (
        <div className="px-4 mb-3">
          <button
            type="button"
            onClick={toggleAll}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <CheckSquare className="w-3.5 h-3.5 inline mr-1" />
            全选 ({submissions.length} 条)
          </button>
        </div>
      )}

      {/* 队列列表 */}
      <div className="px-4 space-y-3">
        {submissions.map((submission) => (
          <ReviewQueueItemCard
            key={submission.submission_id}
            submission={submission}
            onClick={() => onItemClick(submission.submission_id)}
            isSelected={selectedIds.has(submission.submission_id)}
            onSelect={() => toggleSelection(submission.submission_id)}
          />
        ))}
      </div>
    </>
  )
}