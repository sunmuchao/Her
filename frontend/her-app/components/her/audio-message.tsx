'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Volume2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AudioMessageProps {
  audioUrl: string
  durationMs?: number
  format?: string
  autoPlay?: boolean  // 是否自动播放
  onPlayStart?: () => void
  onPlayEnd?: () => void
  className?: string
}

// 全局音频管理：确保只有一个音频在播放
class AudioManager {
  private static instance: AudioManager
  private currentAudio: HTMLAudioElement | null = null
  private currentId: string | null = null

  static getInstance(): AudioManager {
    if (!AudioManager.instance) {
      AudioManager.instance = new AudioManager()
    }
    return AudioManager.instance
  }

  play(audio: HTMLAudioElement, id: string): void {
    // 停止当前播放的音频
    if (this.currentAudio && this.currentId !== id) {
      this.currentAudio.pause()
      this.currentAudio.currentTime = 0
    }

    this.currentAudio = audio
    this.currentId = id
  }

  stop(id: string): void {
    if (this.currentAudio && this.currentId === id) {
      this.currentAudio.pause()
      this.currentAudio.currentTime = 0
      this.currentAudio = null
      this.currentId = null
    }
  }

  isPlaying(id: string): boolean {
    return Boolean(this.currentId === id && this.currentAudio && !this.currentAudio.paused)
  }
}

const audioManager = AudioManager.getInstance()

function normalizeAudioUrl(audioUrl: string): string {
  const normalized = String(audioUrl || '').trim()
  if (!normalized) return normalized

  if (typeof window === 'undefined') {
    return normalized
  }

  try {
    const parsed = new URL(normalized, window.location.origin)
    const isSameOrigin = parsed.origin === window.location.origin
    if (isSameOrigin) {
      return parsed.toString()
    }

    const localMinioHosts = new Set(['127.0.0.1', 'localhost', '0.0.0.0', 'minio'])
    const isLocalMinio = localMinioHosts.has(parsed.hostname) && parsed.port === '9000'

    if (isLocalMinio) {
      const proxyUrl = new URL('/api/gateway/v1/media/proxy', window.location.origin)
      proxyUrl.searchParams.set('url', parsed.toString())
      return proxyUrl.toString()
    }

    return parsed.toString()
  } catch {
    return normalized
  }
}

export function AudioMessage({
  audioUrl,
  durationMs,
  format: _format,
  autoPlay = false,
  onPlayStart,
  onPlayEnd,
  className,
}: AudioMessageProps) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [hasPlayedOnce, setHasPlayedOnce] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const audioIdRef = useRef<string>(`audio-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`)
  const normalizedAudioUrl = normalizeAudioUrl(audioUrl)

  const startPlayback = useCallback(async (resetToStart: boolean) => {
    if (!audioRef.current) return

    if (resetToStart) {
      audioRef.current.currentTime = 0
    }

    try {
      await audioRef.current.play()
    } catch (error) {
      setIsPlaying(false)
      console.error('[AudioMessage] Audio playback start failed', error)
    }
  }, [])

  const handlePlayClick = () => {
    if (!audioRef.current) return

    if (isPlaying) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioManager.stop(audioIdRef.current)
      return
    }

    void startPlayback(true)
  }

  const handlePlay = () => {
    if (!audioRef.current) return
    setIsPlaying(true)
    audioManager.play(audioRef.current, audioIdRef.current)
    onPlayStart?.()
  }

  const handlePause = () => {
    setIsPlaying(false)
  }

  const handleEnded = () => {
    setIsPlaying(false)
    setHasPlayedOnce(true)
    audioManager.stop(audioIdRef.current)
    onPlayEnd?.()
  }

  const handleError = () => {
    setIsPlaying(false)
    const mediaError = audioRef.current?.error
    console.error('[AudioMessage] Audio playback error', {
      src: audioRef.current?.currentSrc || normalizedAudioUrl,
      code: mediaError?.code,
      message:
        mediaError?.code === MediaError.MEDIA_ERR_ABORTED
          ? 'MEDIA_ERR_ABORTED'
          : mediaError?.code === MediaError.MEDIA_ERR_NETWORK
            ? 'MEDIA_ERR_NETWORK'
            : mediaError?.code === MediaError.MEDIA_ERR_DECODE
              ? 'MEDIA_ERR_DECODE'
              : mediaError?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED
                ? 'MEDIA_ERR_SRC_NOT_SUPPORTED'
                : 'UNKNOWN',
    })
  }

  // 自动播放逻辑
  useEffect(() => {
    if (autoPlay && audioRef.current && !hasPlayedOnce) {
      // 延迟200ms自动播放（避免多个音频同时播放）
      const timer = setTimeout(() => {
        void startPlayback(true)
      }, 200)

      return () => clearTimeout(timer)
    }
  }, [autoPlay, hasPlayedOnce, startPlayback])

  // 组件卸载时停止播放
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
      }
      audioManager.stop(audioIdRef.current)
    }
  }, [])

  return (
    <div className={cn('inline-flex items-center gap-2', className)}>
      {/* 播放按钮 - 更明显的样式 */}
      <button
        onClick={handlePlayClick}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full transition-all',
          isPlaying
            ? 'bg-primary/20 text-primary ring-1 ring-primary/30'
            : 'bg-secondary text-muted-foreground hover:bg-secondary/80 hover:text-foreground',
        )}
        aria-label={isPlaying ? '停止播放' : '播放语音'}
      >
        {isPlaying ? (
          <>
            <Volume2 className="w-4 h-4 animate-pulse" />
            <span className="text-xs font-medium">播放中</span>
          </>
        ) : (
          <>
            <Volume2 className="w-4 h-4" />
            <span className="text-xs font-medium">播放语音</span>
          </>
        )}
      </button>

      {/* 音频时长显示（如果有） */}
      {durationMs && (
        <span className="text-xs text-muted-foreground">
          {Math.round(durationMs / 1000)}秒
        </span>
      )}

      {/* 隐藏的 audio 元素 */}
      <audio
        ref={audioRef}
        src={normalizedAudioUrl}
        onPlay={handlePlay}
        onPause={handlePause}
        onEnded={handleEnded}
        onError={handleError}
        preload="auto"
      />
    </div>
  )
}
