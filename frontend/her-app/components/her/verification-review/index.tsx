'use client'

import { useEffect, useState } from 'react'
import { Clock, FileCheck, FileX, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useVerificationReview } from '@/hooks/use-verification-review'
import { ErrorState } from '@/components/her/ui/error-state'
import { FadeIn } from '@/components/her/ui/animations'
import ReviewQueueList from './review-queue-list'
import ReviewDetailPanel from './review-detail-panel'
import ReviewStatisticsPanel from './review-statistics-panel'

type FieldKeyType = 'education' | 'job' | 'income'

const FIELD_TAB_CONFIG: Record<FieldKeyType, { label: string; key: string }> = {
  education: { label: '学历认证', key: 'education' },
  job: { label: '职业认证', key: 'job' },
  income: { label: '收入认证', key: 'income' },
}

export default function VerificationReviewTab() {
  const [activeField, setActiveField] = useState<FieldKeyType>('education')
  const {
    queue,
    selectedItem,
    loading,
    error,
    isSubmitting,
    submitMessage,
    loadQueue,
    loadDetail,
    handleReview,
    handleBatchReview,
    clearSelection,
    clearMessage,
  } = useVerificationReview()

  // 初始化加载审核队列（根据activeField）
  useEffect(() => {
    void loadQueue(undefined, activeField)
  }, [loadQueue, activeField])

  // 加载状态
  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-muted-foreground">
        <RefreshCw className="h-5 w-5 animate-spin mr-2" />
        加载审核队列...
      </div>
    )
  }

  // 错误状态
  if (error) {
    return (
      <div className="p-6">
        <ErrorState title="无法加载审核队列" message={error} onRetry={() => void loadQueue()} />
        <p className="mt-4 text-xs text-muted-foreground">
          需要 profile_reviewer / platform_admin 角色；本地联调可使用 Gateway legacy API key。
        </p>
      </div>
    )
  }

  // 空状态
  if (!queue || queue.submissions.length === 0) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-6">
        <div className="w-16 h-16 rounded-full bg-gold/10 flex items-center justify-center mb-4">
          <FileCheck className="w-8 h-8 text-gold" />
        </div>
        <h3 className="font-serif text-lg text-foreground mb-2">暂无待审核任务</h3>
        <p className="text-sm text-muted-foreground mb-4">当前没有待审核的学历认证提交</p>
        <button
          type="button"
          onClick={() => void loadQueue()}
          className="rounded-xl border border-border px-4 py-2 text-sm hover:bg-muted/30 transition-colors"
        >
          <RefreshCw className="h-4 w-4 inline mr-2" />
          刷新队列
        </button>
      </div>
    )
  }

  return (
    <div className="pb-6">
      {/* 审核统计 */}
      <ReviewStatisticsPanel />

      {/* 字段类型子Tab切换 */}
      <FadeIn>
        <div className="px-4 pt-2 mb-3">
          <div className="flex gap-2 bg-muted/30 rounded-xl p-1">
            {Object.entries(FIELD_TAB_CONFIG).map(([key, config]) => (
              <button
                key={key}
                type="button"
                onClick={() => setActiveField(key as FieldKeyType)}
                className={cn(
                  'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-all',
                  activeField === key
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {config.label}
              </button>
            ))}
          </div>
        </div>
      </FadeIn>

      {/* 头部统计 */}
      <FadeIn>
        <div className="px-4 pt-2 mb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span>{FIELD_TAB_CONFIG[activeField].label}待审核: {queue.submissions.length} 条</span>
            </div>
            <button
              type="button"
              onClick={() => void loadQueue(undefined, activeField)}
              className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label="刷新队列"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </FadeIn>

      {/* 审核队列列表 */}
      <ReviewQueueList
        submissions={queue.submissions}
        onItemClick={(id) => void loadDetail(id)}
        onBatchReview={(ids, decision) => void handleBatchReview(ids, decision)}
      />

      {/* 审核详情面板 */}
      {selectedItem && (
        <ReviewDetailPanel
          submission={selectedItem}
          isOpen={!!selectedItem}
          isSubmitting={isSubmitting}
          submitMessage={submitMessage}
          onClose={clearSelection}
          onReview={handleReview}
          onClearMessage={clearMessage}
        />
      )}
    </div>
  )
}