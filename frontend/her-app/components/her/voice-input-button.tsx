'use client'

import { Mic, MicOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useState, useRef, useCallback } from 'react'
import { useVoiceInput } from '@/hooks/use-voice-input'

interface VoiceInputButtonProps {
  onTranscript: (text: string) => void
  onError?: (error: string) => void
  disabled?: boolean
}

export function VoiceInputButton({ onTranscript, onError, disabled }: VoiceInputButtonProps) {
  const [showRecordingPanel, setShowRecordingPanel] = useState(false)
  const [isCanceling, setIsCanceling] = useState(false)
  const [dragStartY, setDragStartY] = useState(0)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const {
    isRecording,
    startRecording,
    stopRecording,
    cancelRecording,
    recordingDuration,
    isSupported,
    currentVolume,
  } = useVoiceInput({
    onTranscript: (text) => {
      setShowRecordingPanel(false)
      onTranscript(text)
    },
    onError: (error) => {
      setShowRecordingPanel(false)
      onError?.(error)
    },
    maxDurationMs: 60000, // 最大60秒
    onVolumeChange: () => {
      // 音量变化时自动更新currentVolume状态，用于波形动画
    },
  })

  // 按下开始录音
  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (disabled || !isSupported || isRecording) return

    e.preventDefault()
    setDragStartY(e.clientY)
    setIsCanceling(false)
    setShowRecordingPanel(true)

    void startRecording()
  }, [disabled, isSupported, isRecording, startRecording])

  // 松开停止或取消录音
  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (!isRecording) return

    e.preventDefault()

    // 判断是否上滑取消（上滑超过80px视为取消）
    const dragDistance = dragStartY - e.clientY
    if (dragDistance > 80) {
      cancelRecording()
      setShowRecordingPanel(false)
      setIsCanceling(false)
    } else {
      // 【微信式设计】松开后立即关闭录音面板，让用户感觉已发送
      stopRecording()
      setShowRecordingPanel(false)  // 立即关闭面板，不显示"识别中..."等待状态
      setIsCanceling(false)
      // 后台静默处理识别，识别成功后通过onTranscript回调发送消息
    }
  }, [isRecording, dragStartY, cancelRecording, stopRecording])

  // 拖动检测上滑取消
  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isRecording) return

    const dragDistance = dragStartY - e.clientY
    // 上滑超过80px显示取消状态
    setIsCanceling(dragDistance > 80)
  }, [isRecording, dragStartY])

  // 按钮失焦或离开时取消录音（防止意外情况）
  const handlePointerCancel = useCallback(() => {
    if (isRecording) {
      cancelRecording()
      setShowRecordingPanel(false)
      setIsCanceling(false)
    }
  }, [isRecording, cancelRecording])

  // 格式化录音时长
  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  // 生成音量波形条（8个动态条）
  const renderVolumeBars = () => {
    const bars = []
    for (let i = 0; i < 8; i++) {
      // 基于音量值动态调整高度（最小10%，最大90%）
      const height = Math.max(10, Math.min(90, currentVolume * 0.9))
      bars.push(
        <div
          key={i}
          className="w-1 bg-primary rounded-full transition-all duration-100"
          style={{
            height: `${height}%`,
            opacity: 0.3 + (currentVolume / 100) * 0.7,
          }}
        />
      )
    }
    return bars
  }

  return (
    <>
      {/* 麦克风按钮 */}
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled || !isSupported}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerMove={handlePointerMove}
        onPointerCancel={handlePointerCancel}
        onPointerLeave={handlePointerCancel}
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center transition-all touch-none select-none',
          isRecording
            ? 'bg-primary scale-110 animate-pulse'
            : 'bg-muted hover:bg-primary/10',
          disabled && 'opacity-50 cursor-not-allowed',
          !isSupported && 'opacity-50 cursor-not-allowed'
        )}
        aria-label={isRecording ? '录音中，松开发送' : '按住说话'}
      >
        {isSupported ? (
          <Mic className={cn('w-5 h-5', isRecording ? 'text-primary-foreground' : 'text-muted-foreground')} />
        ) : (
          <MicOff className="w-5 h-5 text-muted-foreground" />
        )}
      </button>

      {/* 录音状态面板 */}
      {showRecordingPanel && (
        <div className="fixed inset-x-0 bottom-0 z-50 bg-background border-t border-border safe-area-bottom animate-slide-up">
          <div className="px-4 py-6 flex flex-col items-center gap-4">
            {/* 取消提示（上滑时显示） */}
            {isCanceling && (
              <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2 text-destructive animate-fade-in">
                <div className="w-8 h-8 rounded-full bg-destructive/10 flex items-center justify-center">
                  <MicOff className="w-4 h-4" />
                </div>
                <span className="text-sm font-medium">松开取消发送</span>
              </div>
            )}

            {/* 音量波形动画 */}
            <div className="flex items-center justify-center gap-1.5 h-12 w-32">
              {renderVolumeBars()}
            </div>

            {/* 录音时长 */}
            <div className="flex items-center gap-2">
              <div className={cn(
                'w-3 h-3 rounded-full animate-pulse',
                isCanceling ? 'bg-destructive' : 'bg-primary'
              )} />
              <span className={cn(
                'text-sm font-medium tabular-nums',
                isCanceling ? 'text-destructive' : 'text-muted-foreground'
              )}>
                {formatDuration(recordingDuration)}
              </span>
              {/* 微信式设计：只在上滑取消时显示提示，正常录音时不显示文字 */}
              {isCanceling && (
                <span className="text-xs text-destructive">松开取消</span>
              )}
              {/* 音量过低警告（帮助用户调整） */}
              {!isCanceling && currentVolume < 5 && (
                <span className="text-xs text-warning">请靠近麦克风</span>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}