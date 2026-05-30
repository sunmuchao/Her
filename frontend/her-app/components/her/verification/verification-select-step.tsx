'use client'

import { ArrowLeft, CheckCircle, Clock, Upload, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FadeIn, PageTransition } from '@/components/her/ui/animations'
import { ProgressRing } from '@/components/her/ui/progress-ring'
import { ErrorState } from '@/components/her/ui/error-state'
import type { FieldItem, VerificationStep } from './use-verification-flow'

interface VerificationSelectStepProps {
  verifiedCount: number
  progress: number
  fieldVerificationTypes: FieldItem[]
  loadError: string | null
  isLoading: boolean
  onBack: () => void
  onStartVideoVerification: () => void
  onStartFieldVerification: (fieldId: string) => void
  getStatusStyles: (status: string) => { bg: string; text: string; icon: string }
  getStatusText: (status: string) => string
}

export function VerificationSelectStep({
  verifiedCount,
  progress,
  fieldVerificationTypes,
  loadError,
  isLoading,
  onBack,
  onStartVideoVerification,
  onStartFieldVerification,
  getStatusStyles,
  getStatusText,
}: VerificationSelectStepProps) {
  return (
    <PageTransition className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button
            onClick={onBack}
            className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors focus-ring"
            aria-label="返回"
          >
            <ArrowLeft className="w-5 h-5 text-foreground" />
          </button>
          <h1 className="font-medium text-foreground">去认证</h1>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-6 space-y-4">
        {loadError && (
          <ErrorState message={loadError} onRetry={() => window.location.reload()} />
        )}
        {isLoading && !loadError && (
          <p className="text-sm text-muted-foreground px-1">正在同步认证状态…</p>
        )}

        <FadeIn>
          <div className="flex items-center gap-4 p-4 bg-card border border-border rounded-xl">
            <ProgressRing progress={progress} size={56} strokeWidth={4} color="rose" showPercentage />
            <div>
              <h2 className="font-medium">认证进度</h2>
              <p className="text-sm text-muted-foreground">{verifiedCount}/{fieldVerificationTypes.length} 项已完成</p>
            </div>
          </div>
        </FadeIn>

        <p className="text-sm text-muted-foreground">
          完成认证可提升你的可信度，让更多优质用户愿意了解你
        </p>

        {fieldVerificationTypes.map((field, index) => {
          const styles = getStatusStyles(field.status)
          return (
            <FadeIn key={field.id} delay={index * 50}>
              <button
                onClick={() => {
                  if (field.id === 'video' && field.status !== 'verified') {
                    onStartVideoVerification()
                  } else if (field.status === 'unverified') {
                    onStartFieldVerification(field.id)
                  }
                }}
                disabled={field.status === 'verified'}
                className={cn(
                  'w-full bg-card rounded-xl p-4 border border-border transition-all text-left focus-ring',
                  field.status !== 'verified' && 'hover:bg-secondary/30 hover:border-primary/20'
                )}
                aria-label={`${field.name}：${getStatusText(field.status)}`}
              >
                <div className="flex items-center gap-3">
                  <div className={cn('w-10 h-10 rounded-full flex items-center justify-center', styles.bg)}>
                    {field.status === 'verified' ? (
                      <CheckCircle className={cn('w-5 h-5', styles.icon)} />
                    ) : field.status === 'pending' ? (
                      <Clock className={cn('w-5 h-5', styles.icon)} />
                    ) : (
                      <Upload className={cn('w-5 h-5', styles.icon)} />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-medium text-foreground">{field.name}</h3>
                      <span className={cn('text-[10px] px-1.5 py-0.5 rounded', styles.bg, styles.text)}>
                        {getStatusText(field.status)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{field.description}</p>
                  </div>
                  {field.status === 'unverified' && (
                    <ChevronRight className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
                  )}
                </div>
              </button>
            </FadeIn>
          )
        })}
      </div>
    </PageTransition>
  )
}