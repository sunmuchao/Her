'use client'

import { useState, type ReactNode, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { ArrowLeft, CheckCircle, FileText, Image, Send, XCircle, AlertTriangle, RefreshCw, User } from 'lucide-react'
import { ImageCarousel } from '@/components/her/ui/image-carousel'
import ReviewHistoryList from './review-history-list'
import { useUserInfo } from '@/hooks/use-user-info'
import type { VerificationEvidence, VerificationSubmissionDetail, ReviewActionParams } from '@/lib/api/endpoints/field-verification'

// 动态导入 PDFPreview，避免 SSR 时加载 pdfjs-dist
const PDFPreview = ({ fileUrl }: { fileUrl: string }) => {
  const [PDFComponent, setPDFComponent] = useState<ReactNode>(null)

  useEffect(() => {
    import('./pdf-preview').then((module) => {
      setPDFComponent(<module.PDFPreview fileUrl={fileUrl} />)
    }).catch(() => {
      setPDFComponent(<div className="text-xs text-muted-foreground">PDF 加载失败</div>)
    })
  }, [fileUrl])

  return PDFComponent || <div className="text-xs text-muted-foreground">PDF 加载中...</div>
}

type ReviewDetailPanelProps = {
  submission: VerificationSubmissionDetail
  isOpen: boolean
  isSubmitting: boolean
  submitMessage: string | null
  onClose: () => void
  onReview: (params: ReviewActionParams) => void
  onClearMessage: () => void
}

const EDUCATION_OPTIONS = [
  { value: '高中', label: '高中' },
  { value: '大专', label: '大专' },
  { value: '本科', label: '本科' },
  { value: '硕士', label: '硕士' },
  { value: '博士', label: '博士' },
]

const JOB_OPTIONS = [
  { value: '程序员', label: '程序员' },
  { value: '医生', label: '医生' },
  { value: '教师', label: '教师' },
  { value: '工程师', label: '工程师' },
  { value: '设计师', label: '设计师' },
  { value: '销售', label: '销售' },
  { value: '其他', label: '其他' },
]

const INCOME_OPTIONS = [
  { value: '5万以下', label: '5万以下' },
  { value: '5-10万', label: '5-10万' },
  { value: '10-20万', label: '10-20万' },
  { value: '20-50万', label: '20-50万' },
  { value: '50万以上', label: '50万以上' },
]

const FIELD_OPTIONS_MAP: Record<string, Array<{ value: string; label: string }>> = {
  education: EDUCATION_OPTIONS,
  job: JOB_OPTIONS,
  income: INCOME_OPTIONS,
}

const REQUESTED_DOCUMENTS_OPTIONS = [
  { value: '毕业证', label: '毕业证' },
  { value: '学位证', label: '学位证' },
  { value: '学信网截图', label: '学信网截图' },
  { value: '在读证明', label: '在读证明' },
]

export default function ReviewDetailPanel({
  submission,
  isOpen,
  isSubmitting,
  submitMessage,
  onClose,
  onReview,
  onClearMessage,
}: ReviewDetailPanelProps) {
  const [decision, setDecision] = useState<'approve' | 'reject' | 'request_resubmission' | ''>('')
  const [reviewNote, setReviewNote] = useState('')
  const [approvedValue, setApprovedValue] = useState('')
  const [requestedDocuments, setRequestedDocuments] = useState<string[]>([])

  // 用户信息缓存（React Query）
  const {
    data: userInfo,
    isLoading: loadingUserInfo,
  } = useUserInfo(submission)

  const normalizeEvidenceArray = (evidence: VerificationSubmissionDetail['evidence']): VerificationEvidence[] => {
    if (Array.isArray(evidence)) return evidence
    if (evidence && typeof evidence === 'object') return [evidence as VerificationEvidence]
    return []
  }

  const resolveEvidenceUrl = (evidence: VerificationEvidence) => {
    if (evidence.file_url) return evidence.file_url
    if (evidence.data_base64 && evidence.content_type) {
      return `data:${evidence.content_type};base64,${evidence.data_base64}`
    }
    return ''
  }

  const resolveEvidenceMimeType = (evidence: VerificationEvidence) => {
    return evidence.file_type || evidence.content_type || ''
  }

  // 兼容后端返回单个 evidence 对象和数组两种格式
  const evidenceArray = normalizeEvidenceArray(submission.evidence)
  const reviewsArray = Array.isArray(submission.reviews) ? submission.reviews : []

  // 提取材料图片URL
  const evidenceImages = evidenceArray
    .map((e) => ({ url: resolveEvidenceUrl(e), mimeType: resolveEvidenceMimeType(e) }))
    .filter((e) => e.url && e.mimeType.startsWith('image/'))
    .map((e) => e.url)

  // 提取PDF文件URL
  const evidencePDFs = evidenceArray
    .map((e) => ({ url: resolveEvidenceUrl(e), mimeType: resolveEvidenceMimeType(e) }))
    .filter((e) => e.url && e.mimeType === 'application/pdf')
    .map((e) => e.url)

  const hasImages = evidenceImages.length > 0
  const hasPDFs = evidencePDFs.length > 0
  const hasEvidence = hasImages || hasPDFs
  const normalizedDeclaredValue = submission.declared_value?.trim()
  const declaredValue = normalizedDeclaredValue && normalizedDeclaredValue !== '未知'
    ? normalizedDeclaredValue
    : (userInfo?.education || '未知')

  // 重置表单
  const resetForm = () => {
    setDecision('')
    setReviewNote('')
    setApprovedValue('')
    setRequestedDocuments([])
    onClearMessage()
  }

  // 关闭面板时重置表单
  const handleClose = () => {
    resetForm()
    onClose()
  }

  // 提交审核
  const handleSubmit = () => {
    if (!decision) return

    const params: ReviewActionParams = {
      submissionId: submission.submission_id,
      decision,
      reviewNote: reviewNote.trim() || undefined,
      approvedValue: decision === 'approve' ? approvedValue : undefined,
      requestedDocuments: decision === 'request_resubmission' ? requestedDocuments : undefined,
      validityDays: decision === 'approve' ? 3650 : undefined,
      nextReviewDays: decision === 'approve' ? 3650 : undefined,
    }

    onReview(params)
  }

  // 格式化时间
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

  // 获取提交时间
  const submissionTime = submission.submitted_at || submission.created_at || ''

  if (!isOpen) return null

  const panelContent: ReactNode = (
    <div className="fixed inset-x-0 bottom-0 z-50 bg-background border-t border-border/60 shadow-lg max-h-[85vh] overflow-y-auto">
      {/* 拖动手柄 */}
      <div className="sticky top-0 bg-background border-b border-border/50 px-4 py-3 flex items-center justify-between">
        <button type="button" onClick={handleClose} className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          关闭
        </button>
        <h3 className="font-serif text-lg text-foreground">审核详情</h3>
        <div className="w-8" /> {/* 占位保持标题居中 */}
      </div>

      {/* 用户信息 */}
      <div className="px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-muted/30 flex items-center justify-center overflow-hidden">
            {userInfo?.avatar_url ? (
              <img src={userInfo.avatar_url} alt="" className="w-12 h-12 rounded-full object-cover" />
            ) : (
              <User className="w-6 h-6 text-muted-foreground" />
            )}
          </div>
          <div>
            <p className="font-medium text-foreground">
              {loadingUserInfo ? '加载中...' : userInfo?.user_name || userInfo?.nickname || `Profile #${submission.profile_id}`}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {submission.user_id ? `User ID: ${submission.user_id}` : `提交时间: ${formatTime(submissionTime)}`}
            </p>
            {!loadingUserInfo && !userInfo && (
              <p className="text-xs text-yellow-600 mt-1">
                ⚠️ 无法加载用户详细信息
              </p>
            )}
          </div>
        </div>
      </div>

      {/* 材料预览 */}
      {hasEvidence ? (
        <div className="px-4 py-4 border-b border-border/50">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground mb-3">
            <FileText className="h-4 w-4" />
            提交材料
          </div>

          {/* 图片材料 */}
          {hasImages && (
            <div className="mb-4">
              <p className="text-xs text-muted-foreground mb-2">图片材料</p>
              <ImageCarousel images={evidenceImages} alt="学历证书" aspectRatio="portrait" showIndicators indicatorStyle="dots" />
            </div>
          )}

          {/* PDF材料 */}
          {hasPDFs && (
            <div className="space-y-4">
              {evidencePDFs.map((pdfUrl, index) => (
                <div key={pdfUrl}>
                  <p className="text-xs text-muted-foreground mb-2">PDF材料 {index + 1}</p>
                  <PDFPreview fileUrl={pdfUrl} />
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="px-4 py-4 border-b border-border/50">
          <div className="rounded-xl bg-yellow-500/10 border border-yellow-500/30 p-3">
            <div className="flex items-center gap-2 text-sm text-yellow-600">
              <AlertTriangle className="h-4 w-4" />
              <span>该用户未上传审核材料</span>
            </div>
            <p className="text-xs text-yellow-600/80 mt-2">
              可能是用户选择了"自申报"方式，或材料上传失败。请根据申报信息判断是否需要补件。
            </p>
          </div>
        </div>
      )}

      {/* 用户申报信息 */}
      <div className="px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground mb-2">
          <FileText className="h-4 w-4" />
          申报信息
        </div>
        <div className="rounded-xl bg-muted/30 p-3 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">申报学历:</span>
            <span className="text-foreground font-medium">{declaredValue}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">审核次数:</span>
            <span className="text-foreground">{submission.review_count}</span>
          </div>
        </div>
      </div>

      {/* 审核历史记录 */}
      {reviewsArray.length > 0 && (
        <div className="px-4 py-3 border-b border-border/50">
          <ReviewHistoryList reviews={reviewsArray} />
        </div>
      )}

      {/* 审核操作表单 */}
      <div className="px-4 py-4">
        <div className="space-y-4">
          {/* 审核决定选择 */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">审核决定</label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setDecision('approve')}
                className={`rounded-xl border px-3 py-2.5 text-sm flex items-center justify-center gap-1 transition-all ${
                  decision === 'approve'
                    ? 'bg-green-500/10 border-green-500 text-green-600'
                    : 'border-border hover:border-border/80'
                }`}
              >
                <CheckCircle className="h-4 w-4" />
                通过
              </button>
              <button
                type="button"
                onClick={() => setDecision('reject')}
                className={`rounded-xl border px-3 py-2.5 text-sm flex items-center justify-center gap-1 transition-all ${
                  decision === 'reject'
                    ? 'bg-rose/10 border-rose text-rose'
                    : 'border-border hover:border-border/80'
                }`}
              >
                <XCircle className="h-4 w-4" />
                驳回
              </button>
              <button
                type="button"
                onClick={() => setDecision('request_resubmission')}
                className={`rounded-xl border px-3 py-2.5 text-sm flex items-center justify-center gap-1 transition-all ${
                  decision === 'request_resubmission'
                    ? 'bg-orange-500/10 border-orange-500 text-orange-600'
                    : 'border-border hover:border-border/80'
                }`}
              >
                <AlertTriangle className="h-4 w-4" />
                补件
              </button>
            </div>
          </div>

          {/* 动态字段 - 通过 */}
          {decision === 'approve' && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                批准{submission.field_key === 'education' ? '学历' : submission.field_key === 'job' ? '职业' : '收入'}值
              </label>
              <select
                value={approvedValue}
                onChange={(e) => setApprovedValue(e.target.value)}
                className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
              >
                <option value="">请选择</option>
                {(FIELD_OPTIONS_MAP[submission.field_key] || EDUCATION_OPTIONS).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* 动态字段 - 补件 */}
          {decision === 'request_resubmission' && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">需补充文件</label>
              <div className="space-y-2">
                {REQUESTED_DOCUMENTS_OPTIONS.map((doc) => (
                  <label key={doc.value} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={requestedDocuments.includes(doc.value)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setRequestedDocuments([...requestedDocuments, doc.value])
                        } else {
                          setRequestedDocuments(requestedDocuments.filter((d) => d !== doc.value))
                        }
                      }}
                      className="rounded"
                    />
                    {doc.label}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* 审核备注 */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">审核备注</label>
            <textarea
              value={reviewNote}
              onChange={(e) => setReviewNote(e.target.value)}
              placeholder="请填写审核意见..."
              className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm min-h-[80px] resize-none"
            />
          </div>

          {/* 提交消息 */}
          {submitMessage && (
            <div className={`rounded-xl p-3 text-sm ${submitMessage.includes('完成') ? 'bg-green-500/10 text-green-600' : 'bg-rose/10 text-rose'}`}>
              {submitMessage}
            </div>
          )}

          {/* 提交按钮 */}
          <button
            type="button"
            disabled={isSubmitting || !decision}
            onClick={handleSubmit}
            className="w-full rounded-xl bg-primary py-3 text-sm font-medium text-primary-foreground disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                提交中...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                提交审核
              </>
            )}
          </button>
        </div>
      </div>

      {/* 调试信息（开发环境） */}
      {process.env.NODE_ENV === 'development' && (
        <div className="px-4 py-3 border-t border-border/50">
          <details className="rounded-xl bg-muted/20 border border-border/30 p-3">
            <summary className="text-xs font-medium text-muted-foreground cursor-pointer">
              🔍 调试信息（API返回的原始数据）
            </summary>
            <pre className="mt-3 text-xs text-muted-foreground overflow-auto max-h-48">
              {JSON.stringify(submission, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  )

  // Portal渲染避开父容器样式影响
  return createPortal(panelContent, document.body)
}
