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

type RecordingMode = 'pcm' | 'media'

function downsampleBuffer(input: Float32Array, inputSampleRate: number, targetSampleRate: number) {
  if (inputSampleRate === targetSampleRate) {
    return input
  }

  const ratio = inputSampleRate / targetSampleRate
  const outputLength = Math.round(input.length / ratio)
  const output = new Float32Array(outputLength)

  let offsetResult = 0
  let offsetBuffer = 0
  while (offsetResult < output.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio)
    let accum = 0
    let count = 0

    for (let i = offsetBuffer; i < nextOffsetBuffer && i < input.length; i += 1) {
      accum += input[i]
      count += 1
    }

    output[offsetResult] = count > 0 ? accum / count : 0
    offsetResult += 1
    offsetBuffer = nextOffsetBuffer
  }

  return output
}

function encodeWavFromFloat32(samples: Float32Array, sampleRate: number) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: 'audio/wav' })
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
  const shouldIgnoreNextStopRef = useRef(false)
  const recordingModeRef = useRef<RecordingMode | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null)
  const pcmChunksRef = useRef<Float32Array[]>([])
  const pcmSampleRateRef = useRef(16000)

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
    if (processorNodeRef.current) {
      processorNodeRef.current.disconnect()
      processorNodeRef.current.onaudioprocess = null
      processorNodeRef.current = null
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect()
      sourceNodeRef.current = null
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close()
      audioContextRef.current = null
    }
    mediaRecorderRef.current = null
    chunksRef.current = []
    pcmChunksRef.current = []
    recordingModeRef.current = null
    shouldIgnoreNextStopRef.current = false
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
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream
      const AudioContextCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext

      if (AudioContextCtor) {
        const audioContext = new AudioContextCtor()
        await audioContext.resume()

        const sourceNode = audioContext.createMediaStreamSource(stream)
        const processorNode = audioContext.createScriptProcessor(4096, 1, 1)

        pcmChunksRef.current = []
        pcmSampleRateRef.current = audioContext.sampleRate
        recordingModeRef.current = 'pcm'
        audioContextRef.current = audioContext
        sourceNodeRef.current = sourceNode
        processorNodeRef.current = processorNode

        processorNode.onaudioprocess = (event) => {
          const channelData = event.inputBuffer.getChannelData(0)
          pcmChunksRef.current.push(new Float32Array(channelData))
        }

        sourceNode.connect(processorNode)
        processorNode.connect(audioContext.destination)
      } else {
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
          if (shouldIgnoreNextStopRef.current) {
            cleanup()
            setState('idle')
            return
          }

          const audioBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })

          if (audioBlob.size === 0) {
            cleanup()
            onError?.('录音时间太短或未采集到声音，请再试一次')
            setState('idle')
            return
          }

          cleanup()
          void processAudioViaWhisper(audioBlob)
        }

        recorder.onerror = () => {
          onError?.('录音失败')
          cleanup()
          setState('idle')
        }

        mediaRecorderRef.current = recorder
        chunksRef.current = []
        recordingModeRef.current = 'media'
        recorder.start(250)
      }

      setState('recording')
      startTimeRef.current = Date.now()

      timerRef.current = setInterval(() => {
        setRecordingDuration(Date.now() - startTimeRef.current)
      }, 100)

      maxDurationTimerRef.current = setTimeout(() => {
        if (recordingModeRef.current === 'media') {
          const recorder = mediaRecorderRef.current
          if (recorder?.state === 'recording') {
            recorder.stop()
          }
        } else if (recordingModeRef.current === 'pcm') {
          const mergedLength = pcmChunksRef.current.reduce((sum, chunk) => sum + chunk.length, 0)
          const merged = new Float32Array(mergedLength)
          let offset = 0
          for (const chunk of pcmChunksRef.current) {
            merged.set(chunk, offset)
            offset += chunk.length
          }

          const downsampled = downsampleBuffer(merged, pcmSampleRateRef.current, 16000)
          const audioBlob = encodeWavFromFloat32(downsampled, 16000)

          if (audioBlob.size === 0) {
            cleanup()
            onError?.('录音时间太短或未采集到声音，请再试一次')
            setState('idle')
            return
          }

          cleanup()
          setState('processing')
          void processAudioViaWhisper(audioBlob)
        }
      }, maxDurationMs)
    } catch (err) {
      console.error('[useVoiceInput] Failed to start recording:', err)
      onError?.('无法访问麦克风，请检查权限设置')
      setState('idle')
    }
  }, [state, onError, maxDurationMs, cleanup, processAudioViaWhisper])

  const stopRecording = useCallback(() => {
    if (state !== 'recording') return

    const recorder = mediaRecorderRef.current
    if (recordingModeRef.current === 'media') {
      if (recorder && recorder.state === 'recording') {
        if (typeof recorder.requestData === 'function') {
          recorder.requestData()
        }
        recorder.stop()
      }
    } else if (recordingModeRef.current === 'pcm') {
      const mergedLength = pcmChunksRef.current.reduce((sum, chunk) => sum + chunk.length, 0)
      const merged = new Float32Array(mergedLength)
      let offset = 0
      for (const chunk of pcmChunksRef.current) {
        merged.set(chunk, offset)
        offset += chunk.length
      }

      const downsampled = downsampleBuffer(merged, pcmSampleRateRef.current, 16000)
      const audioBlob = encodeWavFromFloat32(downsampled, 16000)

      if (audioBlob.size === 0) {
        cleanup()
        onError?.('录音时间太短或未采集到声音，请再试一次')
        setState('idle')
        return
      }

      cleanup()
      void processAudioViaWhisper(audioBlob)
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
    if (recordingModeRef.current === 'media') {
      if (recorder && recorder.state === 'recording') {
        shouldIgnoreNextStopRef.current = true
        recorder.stop()
      }
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
