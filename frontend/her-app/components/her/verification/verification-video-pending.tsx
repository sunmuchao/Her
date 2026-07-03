'use client'

import { AlertTriangle, BadgeCheck, Clock, RotateCcw, ShieldAlert } from 'lucide-react'
import { PageTransition } from '@/components/her/ui/animations'
import type { VerificationNotification, VerificationSubmission } from '@/lib/api/endpoints/verification'
import { getConfidenceLabel, getVideoStatusPresentation } from './verification-helpers'

interface VerificationVideoPendingProps {
  submission?: VerificationSubmission | null
  latestNotification?: VerificationNotification | null
  onBack: () => void
  onRestart: () => void
}

export function VerificationVideoPending({
  submission,
  latestNotification,
  onBack,
  onRestart,
}: VerificationVideoPendingProps) {
  const presentation = getVideoStatusPresentation({
    submission,
    notification: latestNotification,
  })
  const confidenceLabel = getConfidenceLabel(submission?.confidence_band)

  const icon =
    presentation.tone === 'success' ? (
      <BadgeCheck className="w-8 h-8 text-emerald-600" />
    ) : presentation.tone === 'warning' ? (
      <AlertTriangle className="w-8 h-8 text-amber-600" />
    ) : presentation.tone === 'danger' ? (
      <ShieldAlert className="w-8 h-8 text-rose-600" />
    ) : (
      <Clock className="w-8 h-8 text-gold" />
    )

  return (
    <PageTransition className="h-full bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="font-medium text-foreground">身份认证状态</h1>
        </div>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
        <div className="w-16 h-16 rounded-full bg-gold/10 flex items-center justify-center mb-6">
          {icon}
        </div>
        <h2 className="font-serif text-xl text-foreground mb-3">{presentation.title}</h2>
        <p className="text-sm text-muted-foreground mb-2">{presentation.summary}</p>
        <div className="w-full rounded-2xl bg-secondary/60 p-4 text-left mt-4 mb-8">
          <p className="text-sm font-medium text-foreground mb-2">当前回执</p>
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>状态：{submission?.status || 'submitted'}</p>
            {submission?.recommended_decision ? <p>机器建议：{submission.recommended_decision}</p> : null}
            {confidenceLabel ? <p>置信度：{confidenceLabel}</p> : null}
            {submission?.recommended_next_step ? <p>下一步：{submission.recommended_next_step}</p> : null}
            {latestNotification?.body ? <p>最近通知：{latestNotification.body}</p> : null}
          </div>
        </div>
        {presentation.tone === 'warning' || presentation.tone === 'danger' ? (
          <button
            onClick={onRestart}
            className="w-full py-4 mb-3 bg-primary rounded-2xl text-primary-foreground font-medium flex items-center justify-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            {presentation.ctaLabel}
          </button>
        ) : null}
        <button onClick={onBack} className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium">
          {presentation.tone === 'success' ? '返回资料页' : '我知道了'}
        </button>
      </div>
    </PageTransition>
  )
}
