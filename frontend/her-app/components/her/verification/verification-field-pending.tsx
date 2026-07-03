'use client'

import { AlertTriangle, CheckCircle, Clock } from 'lucide-react'
import { PageTransition } from '@/components/her/ui/animations'
import type { FieldVerificationSubmission, VerificationSubmissionDetail } from '@/lib/api/endpoints/field-verification'

interface VerificationFieldPendingProps {
  latestSubmission?: VerificationSubmissionDetail | FieldVerificationSubmission | null
  selectedField?: string | null
  onBack: () => void
  onResubmit: () => void
}

const FIELD_LABELS: Record<string, string> = {
  education: '学历认证',
  occupation: '职业认证',
  job: '职业认证',
  income: '收入认证',
}

const FIELD_STATUS_LABELS: Record<string, string> = {
  submitted: '已提交',
  under_review: '审核中',
  approved: '已通过',
  rejected: '已驳回',
  resubmission_required: '需补件',
  expired: '已过期',
  awaiting_submission: '待提交',
}

export function VerificationFieldPending({
  latestSubmission,
  selectedField,
  onBack,
  onResubmit,
}: VerificationFieldPendingProps) {
  const status = String(latestSubmission?.status || 'submitted').toLowerCase()
  const fieldKey = String(latestSubmission?.field_key || selectedField || '').toLowerCase()
  const fieldName = FIELD_LABELS[fieldKey] || FIELD_LABELS[selectedField || ''] || '材料认证'
  const statusLabel = FIELD_STATUS_LABELS[status] || (latestSubmission?.status || '已提交')
  const latestReview =
    Array.isArray((latestSubmission as VerificationSubmissionDetail | undefined)?.reviews) &&
    (latestSubmission as VerificationSubmissionDetail).reviews!.length > 0
      ? (latestSubmission as VerificationSubmissionDetail).reviews![(latestSubmission as VerificationSubmissionDetail).reviews!.length - 1]
      : null
  const failureReason = latestReview?.review_note?.trim()
  const showResubmit = ['rejected', 'resubmission_required', 'expired', 'awaiting_submission'].includes(status)

  const tone =
    status === 'approved'
      ? {
          title: '审核通过',
          description: '认证结果已更新到资料页。',
          icon: <CheckCircle className="w-8 h-8 text-primary" />,
        }
      : status === 'rejected'
        ? {
            title: '认证未通过',
            description: failureReason || '请根据审核意见补充材料后重新提交。',
            icon: <AlertTriangle className="w-8 h-8 text-destructive" />,
          }
        : status === 'resubmission_required'
          ? {
              title: '需要补件',
              description: failureReason || '请根据审核意见补充材料后重新提交。',
              icon: <AlertTriangle className="w-8 h-8 text-amber-600" />,
            }
          : status === 'expired'
            ? {
                title: '认证已过期',
                description: '请重新提交最新材料。',
                icon: <AlertTriangle className="w-8 h-8 text-amber-600" />,
              }
            : status === 'awaiting_submission'
              ? {
                  title: '等待提交',
                  description: '请按要求上传对应材料。',
                  icon: <AlertTriangle className="w-8 h-8 text-amber-600" />,
                }
              : {
                  title: '审核中',
                  description: '材料已进入审核流程。',
                  icon: <Clock className="w-8 h-8 text-primary" />,
                }

  return (
    <PageTransition className="h-full bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="font-medium text-foreground">{fieldName}</h1>
        </div>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
        <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
          {tone.icon}
        </div>
        <h2 className="font-serif text-xl text-foreground mb-3">{tone.title}</h2>
        <p className="text-sm text-muted-foreground mb-3">{tone.description}</p>
        <div className="w-full rounded-2xl bg-secondary/60 p-4 text-left mt-2 mb-8">
          <div className="space-y-2 text-sm">
            <p className="text-foreground">当前状态：{statusLabel}</p>
            {failureReason ? (
              <div>
                <p className="mb-1 text-foreground">审核意见</p>
                <p className="text-muted-foreground">{failureReason}</p>
              </div>
            ) : null}
          </div>
        </div>
        {showResubmit ? (
          <button onClick={onResubmit} className="w-full py-4 mb-3 bg-primary rounded-2xl text-primary-foreground font-medium">
            重新提交
          </button>
        ) : null}
        <button
          onClick={onBack}
          className={`w-full py-4 rounded-2xl font-medium ${showResubmit ? 'bg-secondary text-foreground' : 'bg-primary text-primary-foreground'}`}
        >
          返回
        </button>
      </div>
    </PageTransition>
  )
}
