'use client'

import { AlertTriangle, CheckCircle, Clock } from 'lucide-react'
import { PageTransition } from '@/components/her/ui/animations'
import type { FieldVerificationSubmission } from '@/lib/api/endpoints/field-verification'

interface VerificationFieldPendingProps {
  latestSubmission?: FieldVerificationSubmission | null
  selectedField?: string | null
  onBack: () => void
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
  resubmission_required: '需重新提交',
  expired: '已过期',
  awaiting_submission: '待提交',
}

export function VerificationFieldPending({
  latestSubmission,
  selectedField,
  onBack,
}: VerificationFieldPendingProps) {
  const status = String(latestSubmission?.status || 'submitted').toLowerCase()
  const fieldName = FIELD_LABELS[selectedField || ''] || '材料认证'
  const statusLabel = FIELD_STATUS_LABELS[status] || (latestSubmission?.status || '已提交')

  const tone =
    status === 'approved'
      ? {
          title: '审核通过',
          description: `${fieldName}已通过审核，资料页会自动刷新认证状态。`,
          icon: <CheckCircle className="w-8 h-8 text-primary" />,
        }
      : status === 'rejected'
        ? {
            title: '认证未通过',
            description: `${fieldName}已被驳回，请根据审核意见补充材料后重新提交。`,
            icon: <AlertTriangle className="w-8 h-8 text-destructive" />,
          }
        : status === 'resubmission_required'
          ? {
              title: '需要补充材料',
              description: `${fieldName}当前需要补件，请根据审核意见重新提交。`,
              icon: <AlertTriangle className="w-8 h-8 text-amber-600" />,
            }
          : status === 'expired'
            ? {
                title: '认证已过期',
                description: `${fieldName}认证已过期，请重新提交最新材料。`,
                icon: <AlertTriangle className="w-8 h-8 text-amber-600" />,
              }
            : status === 'awaiting_submission'
              ? {
                  title: '等待提交材料',
                  description: `${fieldName}尚未提交，请按要求上传对应材料。`,
                  icon: <AlertTriangle className="w-8 h-8 text-amber-600" />,
                }
              : {
                  title: '材料已提交',
                  description: `${fieldName}已进入审核流程，系统会先完成机器预审，再视情况转人工复核。`,
                  icon: <Clock className="w-8 h-8 text-primary" />,
                }

  return (
    <PageTransition className="h-full bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="font-medium text-foreground">提交成功</h1>
        </div>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
        <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
          {tone.icon}
        </div>
        <h2 className="font-serif text-xl text-foreground mb-3">{tone.title}</h2>
        <p className="text-sm text-muted-foreground mb-2">{tone.description}</p>
        <div className="w-full rounded-2xl bg-secondary/60 p-4 text-left mt-4 mb-8">
          <p className="text-sm font-medium text-foreground mb-2">当前回执</p>
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>认证项目：{fieldName}</p>
            <p>状态：{statusLabel}</p>
            {latestSubmission?.field_key ? <p>字段键：{latestSubmission.field_key}</p> : null}
          </div>
        </div>
        <button onClick={onBack} className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium">
          返回
        </button>
      </div>
    </PageTransition>
  )
}
