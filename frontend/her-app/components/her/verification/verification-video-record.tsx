'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import type { LiveVideoChallenge } from '@/lib/api/endpoints/verification'
import {
  buildGuideSteps,
  getChallengeRemainingSeconds,
  getRecordingDurationSeconds,
} from './verification-helpers'
import { useLiveFaceChallenge } from './use-live-face-challenge'

interface VerificationVideoRecordProps {
  isRecording: boolean
  recordingTime: number
  currentGuideStepIndex: number
  liveChallenge: LiveVideoChallenge | null
  previewStream: MediaStream | null
  onBack: () => void
  onRecordVideo: () => void
  onCompleteGuideStep: (params?: { score?: number; transcript?: string; provider?: string }) => void
}

export function VerificationVideoRecord({
  isRecording,
  recordingTime,
  currentGuideStepIndex,
  liveChallenge,
  previewStream,
  onBack,
  onRecordVideo,
  onCompleteGuideStep,
}: VerificationVideoRecordProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [nowMs, setNowMs] = useState(Date.now())
  const recordingDurationSeconds = useMemo(() => getRecordingDurationSeconds(liveChallenge), [liveChallenge])
  const guideSteps = useMemo(() => buildGuideSteps(liveChallenge), [liveChallenge])
  const currentStep = guideSteps[currentGuideStepIndex] || null
  const remainingSeconds = getChallengeRemainingSeconds(liveChallenge?.expires_at, nowMs)
  const isChallengeExpired = remainingSeconds !== null && remainingSeconds <= 0
  const recordTitle = isChallengeExpired
    ? '认证已超时，请重新开始'
    : isRecording
      ? currentStep?.instruction || liveChallenge?.challenge_phrase || '请按提示完成动作'
      : '请正对镜头'
  const recordHint = isChallengeExpired
    ? '请返回重新开始'
    : isRecording
      ? currentStep?.kind === 'spoken_code'
        ? '请大声读出数字'
        : '识别中...'
      : ''
  const progress = guideSteps.length > 0 ? Math.min(100, Math.round((currentGuideStepIndex / guideSteps.length) * 100)) : 0
  const spokenAutoAdvanceRef = useRef<number | null>(null)
  const handleActionDetected = useCallback((score: number) => {
    onCompleteGuideStep({ score })
  }, [onCompleteGuideStep])

  const { statusText: detectionStatus } = useLiveFaceChallenge({
    videoRef,
    enabled: isRecording && currentStep?.kind === 'action',
    expectedAction: currentStep?.actionKey,
    onActionDetected: handleActionDetected,
  })

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

  useEffect(() => {
    if (!isRecording || currentStep?.kind !== 'spoken_code') {
      if (spokenAutoAdvanceRef.current !== null) {
        window.clearTimeout(spokenAutoAdvanceRef.current)
        spokenAutoAdvanceRef.current = null
      }
      return
    }

    const SpeechRecognitionCtor =
      typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : undefined

    const normalizeDigits = (input: string) =>
      input
        .replace(/[零〇]/g, '0')
        .replace(/一/g, '1')
        .replace(/二|两/g, '2')
        .replace(/三/g, '3')
        .replace(/四/g, '4')
        .replace(/五/g, '5')
        .replace(/六/g, '6')
        .replace(/七/g, '7')
        .replace(/八/g, '8')
        .replace(/九/g, '9')
        .replace(/\D/g, '')

    if (!SpeechRecognitionCtor) {
      spokenAutoAdvanceRef.current = window.setTimeout(() => {
        onCompleteGuideStep({
          transcript: String(currentStep.spokenCode || ''),
          provider: 'timed_audio_fallback',
        })
      }, 2500)

      return () => {
        if (spokenAutoAdvanceRef.current !== null) {
          window.clearTimeout(spokenAutoAdvanceRef.current)
          spokenAutoAdvanceRef.current = null
        }
      }
    }

    const recognition = new SpeechRecognitionCtor()
    recognition.lang = 'zh-CN'
    recognition.continuous = false
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    recognition.onresult = (event) => {
      let transcript = ''
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index]?.[0]?.transcript || ''
      }
      const normalizedTranscript = normalizeDigits(transcript)
      const normalizedCode = normalizeDigits(String(currentStep.spokenCode || ''))

      if (normalizedCode && normalizedTranscript.includes(normalizedCode)) {
        onCompleteGuideStep({
          transcript: normalizedTranscript,
          provider: 'browser_speech_recognition',
        })
      }
    }

    recognition.start()

    return () => {
      recognition.onresult = null
      recognition.onerror = null
      recognition.onend = null
      recognition.abort()
    }
  }, [currentStep, isRecording, onCompleteGuideStep])

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
          <div className="mb-5 rounded-3xl bg-black/35 px-4 py-4 backdrop-blur-sm">
            <h3 className="text-xl font-medium text-white">{recordTitle}</h3>
            {recordHint ? <p className="mt-2 text-sm text-white/70">{recordHint}</p> : null}
            {isRecording && currentStep?.kind === 'action' && detectionStatus ? (
              <p className="mt-2 text-xs text-white/55">{detectionStatus}</p>
            ) : null}
          </div>
          <div className="mb-4 h-2 w-full max-w-xs rounded-full bg-white/20 overflow-hidden mx-auto">
            <div
              className="h-full rounded-full bg-white transition-all"
              style={{ width: `${isRecording ? progress : 0}%` }}
            />
          </div>
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
