'use client'

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

interface VerificationVideoRecordProps {
  isRecording: boolean
  recordingTime: number
  previewStream: MediaStream | null
  onBack: () => void
  onRecordVideo: () => void
}

export function VerificationVideoRecord({
  isRecording,
  recordingTime,
  previewStream,
  onBack,
  onRecordVideo,
}: VerificationVideoRecordProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

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
          <h3 className="text-white text-xl font-medium mb-2">
            {isRecording ? '请缓慢转动头部' : '准备好后点击开始'}
          </h3>
          <p className="text-white/60 text-sm">
            {isRecording ? `录制中 ${recordingTime}s / 6s` : '确保面部光线充足'}
          </p>
        </div>
        <button
          onClick={() => void onRecordVideo()}
          disabled={isRecording}
          className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
            isRecording ? 'bg-rose animate-pulse' : 'bg-white hover:scale-105'
          }`}
        >
          {isRecording ? <div className="w-8 h-8 rounded-md bg-white" /> : <div className="w-16 h-16 rounded-full bg-primary" />}
        </button>
      </div>
    </div>
  )
}
