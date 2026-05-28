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

function getSpeechRecognitionCtor() {
  if (typeof window === 'undefined') {
    return null
  }
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
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

  const isSupported =
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    !!getSpeechRecognitionCtor()

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

  const processAudio = useCallback(async (audioBlob: Blob) => {
    setState('processing')
    
    // Use Web Speech API for speech-to-text
    const SpeechRecognition = getSpeechRecognitionCtor()
    
    if (!SpeechRecognition) {
      // Fallback: just notify that recording is complete
      onError?.('语音识别不可用，请手动输入')
      setState('idle')
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    // Since Web Speech API works with live audio, we'll use a different approach
    // Create an audio element and play it while recognition listens
    try {
      const audioUrl = URL.createObjectURL(audioBlob)
      const audio = new Audio(audioUrl)
      
      recognition.onresult = (event: SpeechRecognitionEvent) => {
        const transcript = event.results[0][0].transcript
        onTranscript?.(transcript)
        setState('idle')
        URL.revokeObjectURL(audioUrl)
      }

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        console.error('[v0] Speech recognition error:', event.error)
        onError?.('语音识别失败，请重试')
        setState('idle')
        URL.revokeObjectURL(audioUrl)
      }

      recognition.onend = () => {
        if (state === 'processing') {
          setState('idle')
        }
        URL.revokeObjectURL(audioUrl)
      }

      // For recorded audio, we need to play it and have the user's audio reach the mic
      // This is a limitation - Web Speech API only works with live mic input
      // So we'll use a simpler approach: start recognition during recording instead
      onError?.('录音完成，但浏览器语音识别仅支持实时输入')
      setState('idle')
    } catch (err) {
      console.error('[v0] Audio processing error:', err)
      onError?.('音频处理失败')
      setState('idle')
    }
  }, [onTranscript, onError, state])

  const startRecording = useCallback(async () => {
    if (state !== 'idle') return

    // Use Web Speech API directly for real-time speech recognition
    const SpeechRecognition = getSpeechRecognitionCtor()
    
    if (SpeechRecognition) {
      setState('recording')
      startTimeRef.current = Date.now()
      
      timerRef.current = setInterval(() => {
        setRecordingDuration(Date.now() - startTimeRef.current)
      }, 100)

      const recognition = new SpeechRecognition()
      recognition.lang = 'zh-CN'
      recognition.interimResults = true
      recognition.continuous = true
      recognition.maxAlternatives = 1

      let finalTranscript = ''

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let interimTranscript = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript
          if (event.results[i].isFinal) {
            finalTranscript += transcript
          } else {
            interimTranscript += transcript
          }
        }
      }

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        console.error('[v0] Speech recognition error:', event.error)
        if (event.error !== 'aborted') {
          onError?.('语音识别失败，请重试')
        }
        cleanup()
        setState('idle')
      }

      recognition.onend = () => {
        if (finalTranscript) {
          onTranscript?.(finalTranscript)
        }
        cleanup()
        setState('idle')
      }

      // Store recognition in ref for later stopping
      mediaRecorderRef.current = recognition as unknown as MediaRecorder

      maxDurationTimerRef.current = setTimeout(() => {
        recognition.stop()
      }, maxDurationMs)

      try {
        recognition.start()
      } catch (err) {
        console.error('[v0] Failed to start recognition:', err)
        onError?.('无法启动语音识别')
        cleanup()
        setState('idle')
      }
      return
    }

    // Fallback to MediaRecorder if Web Speech API is not available
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

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
        void processAudio(audioBlob)
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

      recorder.start(250)
    } catch (err) {
      console.error('[v0] Failed to start recording:', err)
      onError?.('无法访问麦克风，请检查权限设置')
      setState('idle')
    }
  }, [state, onTranscript, onError, maxDurationMs, cleanup, processAudio])

  const stopRecording = useCallback(() => {
    if (state !== 'recording') return

    // Check if it's a SpeechRecognition instance
    const recorder = mediaRecorderRef.current
    if (recorder) {
      if ('stop' in recorder && typeof recorder.stop === 'function') {
        try {
          recorder.stop()
        } catch (err) {
          console.error('[v0] Error stopping recording:', err)
        }
      }
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
    if (recorder) {
      // Check if it's a SpeechRecognition (has abort method) or MediaRecorder
      if ('abort' in recorder) {
        (recorder as unknown as SpeechRecognition).abort()
      } else if ('state' in recorder && (recorder as MediaRecorder).state === 'recording') {
        (recorder as MediaRecorder).stop()
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
