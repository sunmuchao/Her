'use client'

import { useState, useRef, useCallback, useEffect } from 'react'

export type VoiceInputState = 'idle' | 'recording' | 'processing'

interface UseVoiceInputOptions {
  onTranscript?: (text: string) => void
  onError?: (error: string) => void
  maxDurationMs?: number
}

interface UseVoiceInputReturn {
  state: VoiceInputState
  isRecording: boolean
  isProcessing: boolean
  startRecording: () => Promise<void>
  stopRecording: () => void
  cancelRecording: () => void
  recordingDuration: number
  isSupported: boolean
}

/**
 * 调用后端 Whisper API 进行语音识别
 * 首次使用时模型需要下载，增加超时时间
 */
async function transcribeAudioViaWhisper(audioBlob: Blob): Promise<string> {
  // 首次使用时 Whisper 模型可能需要下载（small 约 500MB，medium 约 1.5GB）
  // 增加超时时间到 120 秒
  const TIMEOUT_MS = 120000

  // 创建 AbortController 用于超时控制
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const response = await fetch('/api/gateway/v1/voice/transcribe', {
      method: 'POST',
      body: audioBlob,
      headers: {
        'Content-Type': audioBlob.type || 'audio/webm',
      },
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      let errorMessage = '语音识别失败'

      try {
        const errorData = await response.json()
        const code = errorData.error?.code
        const message = errorData.error?.message

        if (code === 'audio_dependency_missing' || code === 'audio_conversion_failed') {
          errorMessage = '音频格式转换失败，请检查网关的 ffmpeg、pydub 和 Whisper 依赖'
        } else if (typeof message === 'string' && message.trim()) {
          errorMessage = message
        }
      } catch {
        errorMessage = `语音识别失败 (${response.status})`
      }

      throw new Error(errorMessage)
    }

    const result = await response.json()
    return result.text || ''
  } catch (error) {
    clearTimeout(timeoutId)

    // 处理超时错误
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('语音识别超时，首次使用时模型需要下载，请稍后再试')
    }

    throw error
  }
}

export function useVoiceInput({
  onTranscript,
  onError,
  maxDurationMs = 60000,
}: UseVoiceInputOptions = {}): UseVoiceInputReturn {
  const [state, setState] = useState<VoiceInputState>('idle')
  const [recordingDuration, setRecordingDuration] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startTimeRef = useRef<number>(0)
  const maxDurationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 只需要 MediaRecorder API，不需要 Web Speech API
  const isSupported =
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia

  // DEBUG: 诊断支持情况
  useEffect(() => {
    if (typeof window !== 'undefined') {
      console.log('[useVoiceInput] 支持情况诊断:')
      console.log('  - window:', typeof window !== 'undefined')
      console.log('  - navigator:', typeof navigator !== 'undefined')
      console.log('  - mediaDevices:', !!navigator.mediaDevices)
      console.log('  - getUserMedia:', !!navigator.mediaDevices?.getUserMedia)
      console.log('  - isSupported:', isSupported)
      console.log('  - 方案: 后端 Whisper API')
    }
  }, [isSupported])

  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (maxDurationTimerRef.current) {
      clearTimeout(maxDurationTimerRef.current)
      maxDurationTimerRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    mediaRecorderRef.current = null
    chunksRef.current = []
    setRecordingDuration(0)
  }, [])

  useEffect(() => {
    return () => cleanup()
  }, [cleanup])

  const processAudioViaWhisper = useCallback(async (audioBlob: Blob) => {
    setState('processing')

    try {
      const text = await transcribeAudioViaWhisper(audioBlob)
      if (text.trim()) {
        onTranscript?.(text)
      } else {
        onError?.('未识别到语音内容，请确保麦克风正常工作')
      }
      setState('idle')
    } catch (err) {
      console.error('[useVoiceInput] Whisper transcription error:', err)

      // 根据错误类型提供更友好的提示
      let errorMessage = '语音识别失败，请重试'

      if (err instanceof Error) {
        const msg = err.message

        if (msg.includes('timeout') || msg.includes('超时')) {
          errorMessage = '语音识别超时，首次使用需要下载模型，请稍后再试'
        } else if (msg.includes('ffmpeg') || msg.includes('audio format')) {
          errorMessage = '音频格式不支持，请联系管理员安装 ffmpeg'
        } else if (msg.includes('Invalid data')) {
          errorMessage = '音频数据无效，请检查麦克风是否正常工作'
        } else if (msg.includes('Network') || msg.includes('fetch')) {
          errorMessage = '网络连接失败，请检查网络后重试'
        } else if (msg.includes('未识别')) {
          errorMessage = msg  // 使用原始错误信息
        } else {
          errorMessage = `语音识别失败: ${msg}`
        }
      }

      onError?.(errorMessage)
      setState('idle')
    }
  }, [onTranscript, onError])

  const startRecording = useCallback(async () => {
    if (state !== 'idle') return

    try {
      // 使用 MediaRecorder 录制音频，发送到后端 Whisper API
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // 选择支持的音频格式
      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : ''

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      recorder.onstop = () => {
        const audioBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })

        // DEBUG: 记录音频信息用于诊断
        console.log('[useVoiceInput] Audio recorded:')
        console.log('  - Blob size:', audioBlob.size, 'bytes')
        console.log('  - Blob type:', audioBlob.type)
        console.log('  - Duration:', Date.now() - startTimeRef.current, 'ms')
        console.log('  - Chunks:', chunksRef.current.length)

        void processAudioViaWhisper(audioBlob)
      }

      recorder.onerror = () => {
        onError?.('录音失败')
        cleanup()
        setState('idle')
      }

      mediaRecorderRef.current = recorder
      chunksRef.current = []

      setState('recording')
      startTimeRef.current = Date.now()

      timerRef.current = setInterval(() => {
        setRecordingDuration(Date.now() - startTimeRef.current)
      }, 100)

      maxDurationTimerRef.current = setTimeout(() => {
        if (recorder.state === 'recording') {
          recorder.stop()
        }
      }, maxDurationMs)

      recorder.start(250) // 每 250ms 收集一次数据
    } catch (err) {
      console.error('[useVoiceInput] Failed to start recording:', err)
      onError?.('无法访问麦克风，请检查权限设置')
      setState('idle')
    }
  }, [state, onError, maxDurationMs, cleanup, processAudioViaWhisper])

  const stopRecording = useCallback(() => {
    if (state !== 'recording') return

    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state === 'recording') {
      recorder.stop()
    }

    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (maxDurationTimerRef.current) {
      clearTimeout(maxDurationTimerRef.current)
      maxDurationTimerRef.current = null
    }
  }, [state])

  const cancelRecording = useCallback(() => {
    if (state !== 'recording') return

    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state === 'recording') {
      recorder.stop()
      // 清空录音数据，不发送到后端
      chunksRef.current = []
    }

    cleanup()
    setState('idle')
  }, [state, cleanup])

  return {
    state,
    isRecording: state === 'recording',
    isProcessing: state === 'processing',
    startRecording,
    stopRecording,
    cancelRecording,
    recordingDuration,
    isSupported,
  }
}
