'use client'

import { useState, useEffect, useCallback } from 'react'
import { Clock, RefreshCw, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/api/errors'
import { useVerificationReview } from '@/hooks/use-verification-review'
import {
  fetchVideoReviewQueue,
  fetchReportReviewQueue,
  fetchPhotoRiskQueue,
  fetchAppealReviewQueue,
  reviewVideoVerification,
  reviewReportCase,
  reviewPhotoRisk,
  reviewAppealCase,
  type VideoSubmission,
  type ReportCase,
  type PhotoRiskItem,
  type AppealCase,
} from '@/lib/api/endpoints/all-review-types'
import { ErrorState } from '@/components/her/ui/error-state'
import { FadeIn } from '@/components/her/ui/animations'

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

  // 字段认证审核
  const fieldReview = useVerificationReview()

  // 其他审核类型队列
  const [videoQueue, setVideoQueue] = useState<VideoSubmission[]>([])
  const [reportQueue, setReportQueue] = useState<ReportCase[]>([])
  const [photoQueue, setPhotoQueue] = useState<PhotoRiskItem[]>([])
  const [appealQueue, setAppealQueue] = useState<AppealCase[]>([])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 加载其他审核类型队列
  const loadOtherQueues = useCallback(async (type: ReviewType) => {
    setLoading(true)
    setError(null)
    try {
      switch (type) {
        case 'video':
          const videoData = await fetchVideoReviewQueue()
          setVideoQueue(videoData.submissions)
          break
        case 'report':
          const reportData = await fetchReportReviewQueue()
          setReportQueue(reportData.cases)
          break
        case 'photo':
          const photoData = await fetchPhotoRiskQueue()
          setPhotoQueue(photoData.photos)
          break
        case 'appeal':
          const appealData = await fetchAppealReviewQueue()
          setAppealQueue(appealData.appeals)
          break
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  // 初始化加载
  useEffect(() => {
    if (activeReviewType === 'field') {
      void fieldReview.loadQueue(undefined, activeField)
    } else {
      void loadOtherQueues(activeReviewType)
    }
  }, [activeReviewType, activeField, fieldReview.loadQueue, loadOtherQueues])

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
            activeReviewType === 'field' ? fieldReview.queue?.submissions.length || 0 :
            activeReviewType === 'video' ? videoQueue.length :
            activeReviewType === 'report' ? reportQueue.length :
            activeReviewType === 'photo' ? photoQueue.length :
            appealQueue.length
          } 条</span>
        </div>
        <button
          type="button"
          onClick={() => {
            if (activeReviewType === 'field') {
              void fieldReview.loadQueue(undefined, activeField)
            } else {
              void loadOtherQueues(activeReviewType)
            }
          }}
          className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {/* 队列列表 */}
      {loading ? (
        <div className="text-sm text-muted-foreground text-center py-8">加载中...</div>
      ) : error ? (
        <ErrorState title="加载失败" message={error} onRetry={() => void loadOtherQueues(activeReviewType)} />
      ) : (
        <div className="px-4 space-y-2">
          {/* 字段认证队列 */}
          {activeReviewType === 'field' && fieldReview.queue?.submissions.map((item) => (
            <SimpleQueueCard key={item.submission_id} item={item} onClick={() => alert('使用学历认证审核界面')} />
          ))}

          {/* 活体视频队列 */}
          {activeReviewType === 'video' && videoQueue.map((item) => (
            <SimpleQueueCard key={item.submission_id} item={item} onClick={() => alert('视频审核：' + item.video_url)} />
          ))}

          {/* 举报队列 */}
          {activeReviewType === 'report' && reportQueue.map((item) => (
            <SimpleQueueCard key={item.case_id} item={item} onClick={() => alert('举报审核：' + item.report_reason_text)} />
          ))}

          {/* 照片风险队列 */}
          {activeReviewType === 'photo' && photoQueue.map((item) => (
            <SimpleQueueCard key={item.photo_id} item={item} onClick={() => alert('照片审核：风险评分 ' + item.risk_score)} />
          ))}

          {/* 申诉队列 */}
          {activeReviewType === 'appeal' && appealQueue.map((item) => (
            <SimpleQueueCard key={item.appeal_id} item={item} onClick={() => alert('申诉审核：' + item.appeal_reason)} />
          ))}

          {/* 空状态 */}
          {activeReviewType === 'field' && !fieldReview.queue?.submissions.length && (
            <div className="text-center text-sm text-muted-foreground py-8">
              暂无待审核任务
            </div>
          )}
          {activeReviewType !== 'field' && (
            (activeReviewType === 'video' && videoQueue.length === 0) ||
            (activeReviewType === 'report' && reportQueue.length === 0) ||
            (activeReviewType === 'photo' && photoQueue.length === 0) ||
            (activeReviewType === 'appeal' && appealQueue.length === 0)
          ) && (
            <div className="text-center text-sm text-muted-foreground py-8">
              暂无待审核任务
            </div>
          )}
        </div>
      )}

      {/* 权限提示 */}
      <div className="px-4 mt-6">
        <div className="rounded-xl bg-muted/30 border border-border/40 p-3 text-xs text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5 inline mr-1" />
          需要 profile_reviewer / risk_reviewer / platform_admin 角色
        </div>
      </div>
    </div>
  )
}