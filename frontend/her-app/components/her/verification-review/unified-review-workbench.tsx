'use client'

import { useState } from 'react'
import { Clock, RefreshCw, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/api/errors'
import {
  useFieldReviewQueue,
  useFieldReviewMutation,
  useVideoReviewQueue,
  useReportReviewQueue,
  usePhotoReviewQueue,
  useAppealReviewQueue,
} from '@/hooks/use-review-queues'
import { fetchVerificationDetail } from '@/lib/api/endpoints/field-verification'
import { ErrorState } from '@/components/her/ui/error-state'
import ReviewDetailPanel from './review-detail-panel'
import type { VerificationSubmissionDetail, ReviewActionParams } from '@/lib/api/endpoints/field-verification'

type ReviewType = 'field' | 'video' | 'report' | 'photo' | 'appeal'
type FieldKeyType = 'education' | 'job' | 'income'

const REVIEW_TAB_CONFIG: Record<ReviewType, { label: string }> = {
  field: { label: '字段认证' },
  video: { label: '活体视频' },
  report: { label: '举报审核' },
  photo: { label: '照片风险' },
  appeal: { label: '申诉审核' },
}

const FIELD_TAB_CONFIG: Record<FieldKeyType, { label: string }> = {
  education: { label: '学历' },
  job: { label: '职业' },
  income: { label: '收入' },
}

export default function UnifiedReviewWorkbench() {
  const [activeReviewType, setActiveReviewType] = useState<ReviewType>('field')
  const [activeField, setActiveField] = useState<FieldKeyType>('education')

  // 字段认证审核队列（React Query）
  const {
    data: fieldQueue,
    isLoading: fieldLoading,
    error: fieldError,
    refetch: refetchFieldQueue,
  } = useFieldReviewQueue({
    status: 'submitted,under_review',
    field_key: activeField,
    limit: 20,
  })

  // 其他审核类型队列（React Query）
  const {
    data: videoData,
    isLoading: videoLoading,
    refetch: refetchVideoQueue,
  } = useVideoReviewQueue()

  const {
    data: reportData,
    isLoading: reportLoading,
    refetch: refetchReportQueue,
  } = useReportReviewQueue()

  const {
    data: photoData,
    isLoading: photoLoading,
    refetch: refetchPhotoQueue,
  } = usePhotoReviewQueue()

  const {
    data: appealData,
    isLoading: appealLoading,
    refetch: refetchAppealQueue,
  } = useAppealReviewQueue()

  // 审核操作 mutation
  const reviewMutation = useFieldReviewMutation()

  // 审核详情面板状态
  const [selectedSubmission, setSelectedSubmission] = useState<VerificationSubmissionDetail | null>(null)
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)

  const normalizeSubmissionDetail = (detail: VerificationSubmissionDetail): VerificationSubmissionDetail => ({
    submission_id: detail.submission_id,
    profile_id: detail.profile_id ?? 0,
    user_id: detail.user_id,
    field_key: detail.field_key ?? 'education',
    declared_value: detail.declared_value ?? '未知',
    status: detail.status ?? 'submitted',
    evidence: detail.evidence ?? null,
    source_dsn: detail.source_dsn,
    source_table_name: detail.source_table_name,
    review_count: detail.review_count ?? 0,
    reviews: Array.isArray(detail.reviews) ? detail.reviews : [],
    created_at: detail.created_at,
    updated_at: detail.updated_at,
    submitted_at: detail.submitted_at,
    dispute_status: detail.dispute_status,
    verification_expires_at: detail.verification_expires_at,
    next_review_due_at: detail.next_review_due_at,
    reverify_strategy: detail.reverify_strategy,
  })

  // 打开审核详情面板
  const openReviewPanel = async (submissionId: string) => {
    setSubmitMessage(null)

    try {
      // 调用 API 加载审核详情
      const detail = await fetchVerificationDetail(submissionId)

      // 验证数据是否有效且包含必需字段
      if (detail && typeof detail === 'object' && detail.submission_id) {
        const normalizedDetail = normalizeSubmissionDetail(detail)
        const hasRequiredFields = detail.profile_id != null && !!detail.field_key && detail.declared_value != null

        if (hasRequiredFields) {
          setSelectedSubmission(normalizedDetail)
          setIsPanelOpen(true)
        } else {
          console.warn('审核详情数据不完整:', {
            submission_id: detail.submission_id,
            profile_id: detail.profile_id,
            field_key: detail.field_key,
            declared_value: detail.declared_value,
            evidence: detail.evidence,
          })
          setSelectedSubmission(normalizedDetail)
          setIsPanelOpen(true)
          setSubmitMessage('⚠️ 数据加载不完整，部分信息可能缺失')
        }
      } else {
        // 数据完全无效，不打开面板，显示错误提示
        setSubmitMessage('❌ 加载审核详情失败：返回数据无效')
        alert('加载审核详情失败：返回数据无效')
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '加载审核详情失败'
      setSubmitMessage(errorMsg)
      alert(`加载审核详情失败：${errorMsg}`)
    }
  }

  // 关闭审核详情面板
  const closeReviewPanel = () => {
    setIsPanelOpen(false)
    setSelectedSubmission(null)
    setSubmitMessage(null)
  }

  // 提交审核
  const handleReview = async (params: ReviewActionParams) => {
    setSubmitMessage(null)
    try {
      await reviewMutation.mutateAsync(params)
      setSubmitMessage('审核提交成功')
      // 3秒后关闭面板
      setTimeout(() => {
        closeReviewPanel()
      }, 3000)
    } catch (err) {
      setSubmitMessage(getErrorMessage(err, '审核提交失败'))
    }
  }

  // 清除提交消息
  const clearSubmitMessage = () => {
    setSubmitMessage(null)
  }

  // 简化版审核队列卡片
  const SimpleQueueCard = ({ item, onClick }: { item: any; onClick: () => void }) => (
    <div className="rounded-xl border border-border/60 bg-card/70 p-3 hover:bg-card/90 transition-colors cursor-pointer">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">ID: {item.submission_id || item.case_id || item.photo_id || item.appeal_id}</span>
        <span className="text-muted-foreground">{item.status || 'pending'}</span>
      </div>
      <div className="mt-2 text-sm text-foreground">
        {item.report_reason_text || item.appeal_reason || '点击查看详情'}
      </div>
      <button type="button" onClick={onClick} className="mt-2 text-xs text-primary">
        审核 →
      </button>
    </div>
  )

  // 简化版审核操作面板
  const SimpleReviewPanel = ({ title, onApprove, onReject }: { title: string; onApprove: () => void; onReject: () => void }) => (
    <div className="fixed inset-x-0 bottom-0 bg-background border-t border-border/60 p-4 z-50">
      <p className="text-sm font-medium mb-3">{title}</p>
      <div className="flex gap-2">
        <button type="button" onClick={onApprove} className="flex-1 rounded-xl bg-green-500/10 border border-green-500/30 py-2 text-sm text-green-600">
          ✓ 通过
        </button>
        <button type="button" onClick={onReject} className="flex-1 rounded-xl bg-rose/10 border border-rose/30 py-2 text-sm text-rose">
          ✗ 驳回
        </button>
      </div>
    </div>
  )

  return (
    <div className="pb-6">
      {/* 主Tab切换 */}
      <div className="px-4 pt-4 mb-4">
        <div className="flex gap-2 bg-muted/30 rounded-xl p-1 overflow-x-auto">
          {Object.entries(REVIEW_TAB_CONFIG).map(([key, config]) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveReviewType(key as ReviewType)}
              className={cn(
                'px-4 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all',
                activeReviewType === key
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {config.label}
            </button>
          ))}
        </div>
      </div>

      {/* 字段认证子Tab（仅field类型显示） */}
      {activeReviewType === 'field' && (
        <div className="px-4 mb-4">
          <div className="flex gap-2 bg-muted/20 rounded-lg p-1">
            {Object.entries(FIELD_TAB_CONFIG).map(([key, config]) => (
              <button
                key={key}
                type="button"
                onClick={() => setActiveField(key as FieldKeyType)}
                className={cn(
                  'flex-1 px-3 py-1.5 rounded text-xs font-medium transition-all',
                  activeField === key
                    ? 'bg-primary/80 text-primary-foreground'
                    : 'text-muted-foreground',
                )}
              >
                {config.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 队列头部 */}
      <div className="px-4 mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="h-4 w-4" />
          <span>待审核: {
            activeReviewType === 'field' ? fieldQueue?.submissions.length || 0 :
            activeReviewType === 'video' ? videoData?.submissions.length || 0 :
            activeReviewType === 'report' ? reportData?.cases.length || 0 :
            activeReviewType === 'photo' ? photoData?.photos.length || 0 :
            appealData?.appeals.length || 0
          } 条</span>
        </div>
        <button
          type="button"
          onClick={() => {
            if (activeReviewType === 'field') {
              void refetchFieldQueue()
            } else if (activeReviewType === 'video') {
              void refetchVideoQueue()
            } else if (activeReviewType === 'report') {
              void refetchReportQueue()
            } else if (activeReviewType === 'photo') {
              void refetchPhotoQueue()
            } else {
              void refetchAppealQueue()
            }
          }}
          className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {/* 队列列表 */}
      {fieldLoading || videoLoading || reportLoading || photoLoading || appealLoading ? (
        <div className="text-sm text-muted-foreground text-center py-8">加载中...</div>
      ) : fieldError ? (
        <ErrorState title="加载失败" message={getErrorMessage(fieldError)} onRetry={() => void refetchFieldQueue()} />
      ) : (
        <div className="px-4 space-y-2">
          {/* 字段认证队列 */}
          {activeReviewType === 'field' && fieldQueue?.submissions.map((item: any) => (
            <SimpleQueueCard key={item.submission_id} item={item} onClick={() => openReviewPanel(item.submission_id)} />
          ))}

          {/* 活体视频队列 */}
          {activeReviewType === 'video' && videoData?.submissions.map((item: any) => (
            <SimpleQueueCard key={item.submission_id} item={item} onClick={() => alert('视频审核：' + item.video_url)} />
          ))}

          {/* 举报队列 */}
          {activeReviewType === 'report' && reportData?.cases.map((item: any) => (
            <SimpleQueueCard key={item.case_id} item={item} onClick={() => alert('举报审核：' + item.report_reason_text)} />
          ))}

          {/* 照片风险队列 */}
          {activeReviewType === 'photo' && photoData?.photos.map((item: any) => (
            <SimpleQueueCard key={item.photo_id} item={item} onClick={() => alert('照片审核：风险评分 ' + item.risk_score)} />
          ))}

          {/* 申诉队列 */}
          {activeReviewType === 'appeal' && appealData?.appeals.map((item: any) => (
            <SimpleQueueCard key={item.appeal_id} item={item} onClick={() => alert('申诉审核：' + item.appeal_reason)} />
          ))}

          {/* 空状态 */}
          {activeReviewType === 'field' && !fieldQueue?.submissions.length && (
            <div className="text-center text-sm text-muted-foreground py-8">
              暂无待审核任务
            </div>
          )}
          {activeReviewType !== 'field' && (
            (activeReviewType === 'video' && !videoData?.submissions.length) ||
            (activeReviewType === 'report' && !reportData?.cases.length) ||
            (activeReviewType === 'photo' && !photoData?.photos.length) ||
            (activeReviewType === 'appeal' && !appealData?.appeals.length)
          ) && (
            <div className="text-center text-sm text-muted-foreground py-8">
              暂无待审核任务
            </div>
          )}
        </div>
      )}

      {/* 审核详情面板 */}
      {selectedSubmission && isPanelOpen && (
        <ReviewDetailPanel
          submission={selectedSubmission}
          isOpen={isPanelOpen}
          isSubmitting={reviewMutation.isPending}
          submitMessage={submitMessage}
          onClose={closeReviewPanel}
          onReview={handleReview}
          onClearMessage={clearSubmitMessage}
        />
      )}
    </div>
  )
}
