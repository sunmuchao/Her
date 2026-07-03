'use client'

import { ArrowLeft, Camera } from 'lucide-react'
import { PageTransition } from '@/components/her/ui/animations'

interface VerificationVideoIntroProps {
  isSubmittingVideo: boolean
  liveChallenge: { challenge_phrase?: string } | null
  onBack: () => void
  onStartVideoVerification: () => void
}

export function VerificationVideoIntro({
  isSubmittingVideo,
  liveChallenge,
  onBack,
  onStartVideoVerification,
}: VerificationVideoIntroProps) {
  return (
    <PageTransition className="h-full bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button
            onClick={onBack}
            className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-foreground" />
          </button>
          <h1 className="font-medium text-foreground">身份认证</h1>
        </div>
      </header>

      <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
        <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mb-6">
          <Camera className="w-10 h-10 text-primary" />
        </div>
        <h2 className="font-serif text-xl text-foreground mb-3">验证真实的你</h2>
        <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
          为了保护真实用户的体验，我们需要你完成一个简短的视频认证。开始后系统会生成本次 challenge，包含随机动作，必要时还会要求你读出数字口令。
        </p>
        <div className="w-full rounded-2xl bg-secondary/60 p-4 text-left text-sm text-muted-foreground mb-6 space-y-2">
          <p>录制前请确认：</p>
          <p>1. 光线充足，保持单人出镜。</p>
          <p>2. 录制时按步骤完成动作，不要切出页面。</p>
          <p>3. 如 challenge 包含数字口令，请大声读出屏幕提示。</p>
        </div>
        <button
          type="button"
          disabled={isSubmittingVideo}
          onClick={onStartVideoVerification}
          className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium disabled:opacity-60"
        >
          {isSubmittingVideo ? '准备中…' : '开始认证'}
        </button>
        {liveChallenge?.challenge_phrase && (
          <p className="mt-4 text-sm text-muted-foreground">{liveChallenge.challenge_phrase}</p>
        )}
      </div>
    </PageTransition>
  )
}
