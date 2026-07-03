'use client'

import { ArrowLeft, Camera, RotateCcw } from 'lucide-react'
import { PageTransition } from '@/components/her/ui/animations'
import type { LiveVideoChallenge } from '@/lib/api/endpoints/verification'
import type { RecordedVideo } from '@/lib/media/video-recorder'
import { buildGuideSteps } from './verification-helpers'

interface VerificationVideoReviewProps {
  liveChallenge: LiveVideoChallenge | null
  recordedVideo: RecordedVideo | null
  isSubmittingVideo: boolean
  onBack: () => void
  onSubmit: () => void
  onRerecord: () => void
}

export function VerificationVideoReview({
  liveChallenge,
  recordedVideo,
  isSubmittingVideo,
  onBack,
  onSubmit,
  onRerecord,
}: VerificationVideoReviewProps) {
  const guideSteps = buildGuideSteps(liveChallenge)

  return (
    <PageTransition className="h-full bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button onClick={onBack} className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors">
            <ArrowLeft className="w-5 h-5 text-foreground" />
          </button>
          <h1 className="font-medium text-foreground">确认提交</h1>
        </div>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
        <div className="w-48 h-64 rounded-2xl bg-secondary mb-6 overflow-hidden">
          {recordedVideo?.blobUrl ? (
            <video src={recordedVideo.blobUrl} controls className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full bg-primary/5 flex items-center justify-center">
              <Camera className="w-12 h-12 text-muted-foreground" />
            </div>
          )}
        </div>
        <h2 className="text-lg font-medium text-foreground mb-2">视频录制完成</h2>
        <p className="text-sm text-muted-foreground mb-5">请确认视频清晰，并且 challenge 中的动作和数字口令都已录到视频里。</p>
        <div className="w-full rounded-2xl bg-secondary/60 p-4 text-left mb-8">
          <p className="text-sm font-medium text-foreground mb-2">本次 challenge</p>
          <p className="text-sm text-muted-foreground mb-3">
            {liveChallenge?.challenge_phrase || '系统未返回 challenge 文案'}
          </p>
          <div className="space-y-2">
            {guideSteps.map((step, index) => (
              <div key={step.key} className="rounded-xl bg-background/80 px-3 py-2 text-sm text-foreground">
                {index + 1}. {step.instruction}
              </div>
            ))}
          </div>
        </div>
        <div className="w-full space-y-3">
          <button
            onClick={() => void onSubmit()}
            disabled={isSubmittingVideo || !recordedVideo}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium disabled:opacity-60"
          >
            {isSubmittingVideo ? '提交中…' : '确认提交'}
          </button>
          <button
            onClick={onRerecord}
            className="w-full py-4 bg-secondary rounded-2xl text-foreground font-medium flex items-center justify-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            重新录制
          </button>
        </div>
      </div>
    </PageTransition>
  )
}
