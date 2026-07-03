'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import type { LiveVideoChallenge } from '@/lib/api/endpoints/verification'
import {
  buildGuideSteps,
  formatChallengeDeadline,
  formatRemainingTime,
  getChallengeRemainingSeconds,
  getGuidedRecordingState,
} from './verification-helpers'

interface VerificationVideoRecordProps {
  isRecording: boolean
  recordingTime: number
  liveChallenge: LiveVideoChallenge | null
  previewStream: MediaStream | null
  onBack: () => void
  onRecordVideo: () => void
}

export function VerificationVideoRecord({
  isRecording,
  recordingTime,
  liveChallenge,
  previewStream,
  onBack,
  onRecordVideo,
}: VerificationVideoRecordProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [nowMs, setNowMs] = useState(Date.now())

  const guideState = useMemo(
    () => getGuidedRecordingState({ challenge: liveChallenge, recordingTime }),
    [liveChallenge, recordingTime],
  )
  const guideSteps = useMemo(() => buildGuideSteps(liveChallenge), [liveChallenge])
  const remainingSeconds = getChallengeRemainingSeconds(liveChallenge?.expires_at, nowMs)
  const isChallengeExpired = remainingSeconds !== null && remainingSeconds <= 0
  const previousStep = isRecording && guideState.currentIndex > 0 ? guideSteps[guideState.currentIndex - 1] : null

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.srcObject = previewStream
    if (previewStream) {
      void video.play().catch(() => {})
    }
    return () => {
      if (video) {
        video.srcObject = null
      }
    }
  }, [previewStream])

  return (
    <div className="h-full bg-foreground flex flex-col relative">
      {previewStream ? (
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="absolute inset-0 h-full w-full object-cover scale-x-[-1]"
        />
      ) : null}
      <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-black/45 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-black/60 via-black/25 to-transparent" />
      <div className="absolute inset-0 bg-black/10" />
      <button
        onClick={onBack}
        className="absolute top-12 right-5 w-10 h-10 rounded-full bg-background/20 flex items-center justify-center z-10"
      >
        <X className="w-5 h-5 text-white" />
      </button>
      <div className="relative z-10 flex-1 flex flex-col items-center justify-between py-16 px-8">
        <div className="flex-1 flex items-center justify-center">
          <div className="w-64 h-80 rounded-[40%] border-4 border-dashed border-white/55 flex items-center justify-center bg-black/10">
            {!previewStream ? <p className="text-white/60 text-sm">正在打开摄像头...</p> : null}
          </div>
        </div>
        <div className="text-center mb-8">
          <div className="mb-5 rounded-3xl bg-black/35 px-4 py-3 backdrop-blur-sm">
            <p className="text-white/70 text-xs mb-1">
              {isRecording
                ? `第 ${guideState.currentIndex + 1} / ${Math.max(guideSteps.length, 1)} 步`
                : '准备 challenge'}
            </p>
            <h3 className="text-white text-xl font-medium mb-2">
              {isRecording
                ? guideState.currentStep?.instruction || liveChallenge?.challenge_phrase || '请按屏幕提示完成 challenge'
                : isChallengeExpired
                  ? 'challenge 已过期，请返回重试'
                  : '准备好后点击开始'}
            </h3>
            <p className="text-white/70 text-sm">
              {isRecording
                ? guideState.nextStep
                  ? `下一步：${guideState.nextStep.instruction}`
                  : '最后一步完成后会自动结束录制'
                : isChallengeExpired
                  ? '请退出后重新生成本次 challenge，避免提交时提示超时。'
                  : guideSteps.length > 0
                    ? `本次共 ${guideSteps.length} 步，开始后按顺序逐项完成`
                    : liveChallenge?.challenge_phrase || '系统已生成本次 challenge，开始后请按顺序完成动作'}
            </p>
          </div>
          <div className="mb-4 h-2 w-full max-w-xs rounded-full bg-white/20 overflow-hidden mx-auto">
            <div
              className="h-full rounded-full bg-white transition-all"
              style={{ width: `${isRecording ? guideState.progress : 0}%` }}
            />
          </div>
          {isRecording ? (
            <div className="grid gap-2 text-left max-w-xs mx-auto mb-4 w-full">
              {previousStep ? (
                <div className="rounded-2xl bg-emerald-400/80 px-3 py-2 text-sm text-foreground">
                  已完成：{previousStep.instruction}
                </div>
              ) : null}
              <div className="rounded-2xl bg-white px-3 py-3 text-sm text-foreground">
                当前动作：{guideState.currentStep?.instruction || '请按提示完成'}
              </div>
              {guideState.nextStep ? (
                <div className="rounded-2xl bg-white/10 px-3 py-2 text-sm text-white/70">
                  下一步：{guideState.nextStep.instruction}
                </div>
              ) : null}
            </div>
          ) : null}
          <p className="text-white/60 text-sm">
            {isRecording
              ? `录制中 ${recordingTime}s / 6s`
              : `challenge 有效期至 ${formatChallengeDeadline(liveChallenge?.expires_at)}，剩余 ${formatRemainingTime(remainingSeconds)}`}
          </p>
        </div>
        <button
          onClick={() => void onRecordVideo()}
          disabled={isRecording || isChallengeExpired}
          className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
            isRecording ? 'bg-rose animate-pulse' : isChallengeExpired ? 'bg-white/40' : 'bg-white hover:scale-105'
          }`}
        >
          {isRecording ? <div className="w-8 h-8 rounded-md bg-white" /> : <div className="w-16 h-16 rounded-full bg-primary" />}
        </button>
      </div>
    </div>
  )
}
