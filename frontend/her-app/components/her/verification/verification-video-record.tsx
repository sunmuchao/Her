'use client'

import { X } from 'lucide-react'

interface VerificationVideoRecordProps {
  isRecording: boolean
  recordingTime: number
  onBack: () => void
  onRecordVideo: () => void
}

export function VerificationVideoRecord({
  isRecording,
  recordingTime,
  onBack,
  onRecordVideo,
}: VerificationVideoRecordProps) {
  return (
    <div className="min-h-screen bg-foreground max-w-md mx-auto flex flex-col relative">
      <div className="absolute inset-0 bg-gradient-to-b from-foreground/80 to-foreground" />
      <button
        onClick={onBack}
        className="absolute top-12 right-5 w-10 h-10 rounded-full bg-background/20 flex items-center justify-center z-10"
      >
        <X className="w-5 h-5 text-white" />
      </button>
      <div className="relative z-10 flex-1 flex flex-col items-center justify-between py-16 px-8">
        <div className="flex-1 flex items-center justify-center">
          <div className="w-64 h-80 rounded-[40%] border-4 border-dashed border-white/40 flex items-center justify-center">
            <p className="text-white/60 text-sm">将面部置于框内</p>
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
