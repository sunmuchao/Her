/**
 * Unit tests for useVoiceInput hook with Whisper API integration.
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useVoiceInput } from '../use-voice-input'

// Mock fetch for Whisper API calls
const mockFetch = vi.fn()
global.fetch = mockFetch

// Mock navigator.mediaDevices
const mockGetUserMedia = vi.fn()
const mockMediaRecorder = vi.fn()

beforeEach(() => {
  // Reset mocks
  mockFetch.mockReset()
  mockGetUserMedia.mockReset()
  mockMediaRecorder.mockReset()

  // Setup navigator mock
  Object.defineProperty(global.navigator, 'mediaDevices', {
    value: {
      getUserMedia: mockGetUserMedia,
    },
    writable: true,
  })

  // Setup MediaRecorder mock
  global.MediaRecorder = mockMediaRecorder as any
  mockMediaRecorder.isTypeSupported = vi.fn().mockReturnValue(true)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useVoiceInput', () => {
  describe('support detection', () => {
    it('should return isSupported=true when MediaRecorder API is available', () => {
      mockGetUserMedia.mockResolvedValue({})

      const { result } = renderHook(() => useVoiceInput())

      expect(result.current.isSupported).toBe(true)
    })

    it('should return isSupported=false when MediaRecorder API is not available', () => {
      Object.defineProperty(global.navigator, 'mediaDevices', {
        value: undefined,
        writable: true,
      })

      const { result } = renderHook(() => useVoiceInput())

      expect(result.current.isSupported).toBe(false)
    })
  })

  describe('recording lifecycle', () => {
    it('should start recording when startRecording is called', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'inactive',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const { result } = renderHook(() => useVoiceInput())

      expect(result.current.state).toBe('idle')

      await act(async () => {
        await result.current.startRecording()
      })

      expect(result.current.state).toBe('recording')
      expect(mockRecorder.start).toHaveBeenCalled()
    })

    it('should stop recording when stopRecording is called', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const { result } = renderHook(() => useVoiceInput())

      await act(async () => {
        await result.current.startRecording()
      })

      mockRecorder.state = 'recording'

      act(() => {
        result.current.stopRecording()
      })

      expect(mockRecorder.stop).toHaveBeenCalled()
    })

    it('should cancel recording and clear chunks when cancelRecording is called', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const { result } = renderHook(() => useVoiceInput())

      await act(async () => {
        await result.current.startRecording()
      })

      mockRecorder.state = 'recording'

      act(() => {
        result.current.cancelRecording()
      })

      expect(mockRecorder.stop).toHaveBeenCalled()
      expect(mockFetch).not.toHaveBeenCalled()
      expect(result.current.state).toBe('idle')
    })
  })

  describe('Whisper API integration', () => {
    it('should call Whisper API when recording stops', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const audioChunks = [new Blob(['audio data'], { type: 'audio/webm' })]

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onTranscript = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onTranscript,
          maxDurationMs: 60000,
        }),
      )

      // Start recording
      await act(async () => {
        await result.current.startRecording()
      })

      // Simulate audio data collection
      act(() => {
        if (mockRecorder.ondataavailable) {
          mockRecorder.ondataavailable({ data: audioChunks[0] })
        }
      })

      // Mock Whisper API response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          text: '测试语音识别文本',
          language: 'zh',
          language_probability: 0.98,
          segments: [],
        }),
      })

      // Stop recording
      act(() => {
        result.current.stopRecording()
      })

      // Trigger onstop callback
      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      // Wait for API call
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      // Verify API was called
      expect(mockFetch).toHaveBeenCalledWith('/api/gateway/v1/voice/transcribe', {
        method: 'POST',
        body: audioChunks[0],
        headers: {
          'Content-Type': 'audio/webm',
        },
      })

      // Verify onTranscript was called with result
      expect(onTranscript).toHaveBeenCalledWith('测试语音识别文本')
    })

    it('should handle Whisper API errors gracefully', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const audioChunks = [new Blob(['audio data'], { type: 'audio/webm' })]

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onError,
          maxDurationMs: 60000,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      act(() => {
        if (mockRecorder.ondataavailable) {
          mockRecorder.ondataavailable({ data: audioChunks[0] })
        }
      })

      // Mock API error
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          error: {
            code: 'transcription_failed',
            message: 'Whisper model crashed',
          },
        }),
      })

      act(() => {
        result.current.stopRecording()
      })

      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      expect(onError).toHaveBeenCalledWith('Whisper model crashed')
    })

    it('should map audio conversion failures to actionable error messages', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const audioChunks = [new Blob(['audio data'], { type: 'audio/webm' })]

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onError,
          maxDurationMs: 60000,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      act(() => {
        if (mockRecorder.ondataavailable) {
          mockRecorder.ondataavailable({ data: audioChunks[0] })
        }
      })

      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          error: {
            code: 'audio_conversion_failed',
            message: 'Audio format conversion failed before transcription',
          },
        }),
      })

      act(() => {
        result.current.stopRecording()
      })

      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      expect(onError).toHaveBeenCalledWith('音频格式转换失败，请检查网关的 ffmpeg、pydub 和 Whisper 依赖')
    })

    it('should handle empty transcription result', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const audioChunks = [new Blob(['audio data'], { type: 'audio/webm' })]

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onTranscript = vi.fn()
      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onTranscript,
          onError,
          maxDurationMs: 60000,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      act(() => {
        if (mockRecorder.ondataavailable) {
          mockRecorder.ondataavailable({ data: audioChunks[0] })
        }
      })

      // Mock empty result
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          text: '',
          language: 'zh',
          language_probability: 0.5,
          segments: [],
        }),
      })

      act(() => {
        result.current.stopRecording()
      })

      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      // Should not call onTranscript with empty text
      expect(onTranscript).not.toHaveBeenCalled()
      // Should call onError with message
      expect(onError).toHaveBeenCalledWith('未识别到语音内容')
    })

    it('should not send empty audio blobs to Whisper', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        requestData: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onError,
          maxDurationMs: 60000,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      act(() => {
        result.current.stopRecording()
      })

      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      expect(mockRecorder.requestData).toHaveBeenCalled()
      expect(mockFetch).not.toHaveBeenCalled()
      expect(onError).toHaveBeenCalledWith('录音时间太短或未采集到声音，请再试一次')
    })
  })

  describe('microphone access errors', () => {
    it('should handle microphone permission denied', async () => {
      mockGetUserMedia.mockRejectedValue(new Error('Permission denied'))

      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onError,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      expect(onError).toHaveBeenCalledWith('无法访问麦克风，请检查权限设置')
      expect(result.current.state).toBe('idle')
    })

    it('should handle microphone not found', async () => {
      mockGetUserMedia.mockRejectedValue(new Error('NotFoundError'))

      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onError,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      expect(onError).toHaveBeenCalledWith('无法访问麦克风，请检查权限设置')
      expect(result.current.state).toBe('idle')
    })
  })

  describe('volume detection', () => {
    it('should report volume changes via onVolumeChange callback', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockAudioContext = {
        resume: vi.fn().mockResolvedValue(undefined),
        createMediaStreamSource: vi.fn().mockReturnValue({
          connect: vi.fn(),
        }),
        createAnalyser: vi.fn().mockReturnValue({
          fftSize: 256,
          smoothingTimeConstant: 0.8,
          frequencyBinCount: 128,
          getByteFrequencyData: vi.fn((dataArray) => {
            // Simulate volume level
            for (let i = 0; i < dataArray.length; i++) {
              dataArray[i] = 50 // Medium volume
            }
          }),
          connect: vi.fn(),
        }),
        createScriptProcessor: vi.fn().mockReturnValue({
          onaudioprocess: null,
          connect: vi.fn(),
        }),
        sampleRate: 48000,
        destination: {},
        close: vi.fn().mockResolvedValue(undefined),
      }

      global.AudioContext = vi.fn().mockReturnValue(mockAudioContext) as any
      ;(global as any).webkitAudioContext = undefined

      const onVolumeChange = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onVolumeChange,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      // Wait for volume check timer (100ms interval)
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 150))
      })

      // Should have called onVolumeChange with volume value
      expect(onVolumeChange).toHaveBeenCalled()
      expect(onVolumeChange.mock.calls[0][0]).toBeGreaterThanOrEqual(0)
      expect(onVolumeChange.mock.calls[0][0]).toBeLessThanOrEqual(100)
    })

    it('should report zero volume for silent audio', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockAudioContext = {
        resume: vi.fn().mockResolvedValue(undefined),
        createMediaStreamSource: vi.fn().mockReturnValue({
          connect: vi.fn(),
        }),
        createAnalyser: vi.fn().mockReturnValue({
          fftSize: 256,
          smoothingTimeConstant: 0.8,
          frequencyBinCount: 128,
          getByteFrequencyData: vi.fn((dataArray) => {
            // Simulate silent audio
            for (let i = 0; i < dataArray.length; i++) {
              dataArray[i] = 0 // Zero volume
            }
          }),
          connect: vi.fn(),
        }),
        createScriptProcessor: vi.fn().mockReturnValue({
          onaudioprocess: null,
          connect: vi.fn(),
        }),
        sampleRate: 48000,
        destination: {},
        close: vi.fn().mockResolvedValue(undefined),
      }

      global.AudioContext = vi.fn().mockReturnValue(mockAudioContext) as any

      const onVolumeChange = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onVolumeChange,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 150))
      })

      expect(onVolumeChange).toHaveBeenCalledWith(0)
    })
  })

  describe('hallucination detection', () => {
    it('should filter out YouTube hallucination patterns', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const audioChunks = [new Blob(['audio data'], { type: 'audio/webm' })]

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onTranscript = vi.fn()
      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onTranscript,
          onError,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      act(() => {
        if (mockRecorder.ondataavailable) {
          mockRecorder.ondataavailable({ data: audioChunks[0] })
        }
      })

      // Mock hallucination result (YouTube ending words)
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          text: '请不吝点赞订阅转发打赏支持明镜与点点栏目',
          language: 'zh',
          language_probability: 0.99,
          segments: [],
        }),
      })

      act(() => {
        result.current.stopRecording()
      })

      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      // Backend should filter hallucination and return empty text
      // Frontend should handle empty result
      expect(onTranscript).not.toHaveBeenCalled()
      expect(onError).toHaveBeenCalled()
    })
  })

  describe('network timeout handling', () => {
    it('should handle request timeout gracefully', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const audioChunks = [new Blob(['audio data'], { type: 'audio/webm' })]

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        mimeType: 'audio/webm',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onError = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onError,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      act(() => {
        if (mockRecorder.ondataavailable) {
          mockRecorder.ondataavailable({ data: audioChunks[0] })
        }
      })

      // Mock timeout (AbortError)
      const abortError = new Error('The operation was aborted')
      abortError.name = 'AbortError'
      mockFetch.mockRejectedValue(abortError)

      act(() => {
        result.current.stopRecording()
      })

      await act(async () => {
        if (mockRecorder.onstop) {
          mockRecorder.onstop()
        }
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      expect(onError).toHaveBeenCalledWith('语音识别超时，首次使用时模型需要下载，请稍后再试')
    })
  })

  describe('press-hold mode', () => {
    it('should support press-hold recording mode', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const { result } = renderHook(() => useVoiceInput())

      // Press button (start recording)
      await act(async () => {
        await result.current.startRecording()
      })

      expect(result.current.state).toBe('recording')

      // Hold for some time
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 1000))
      })

      expect(result.current.recordingDuration).toBeGreaterThanOrEqual(1000)

      // Release button (stop recording)
      act(() => {
        result.current.stopRecording()
      })

      expect(mockRecorder.stop).toHaveBeenCalled()
    })

    it('should cancel recording when swipe up detected', async () => {
      const mockStream = {
        getTracks: vi.fn().mockReturnValue([{ stop: vi.fn() }]),
      }
      mockGetUserMedia.mockResolvedValue(mockStream)

      const mockRecorder = {
        start: vi.fn(),
        stop: vi.fn(),
        state: 'recording',
        ondataavailable: null,
        onstop: null,
        onerror: null,
      }
      mockMediaRecorder.mockReturnValue(mockRecorder)

      const onTranscript = vi.fn()

      const { result } = renderHook(() =>
        useVoiceInput({
          onTranscript,
        }),
      )

      await act(async () => {
        await result.current.startRecording()
      })

      expect(result.current.state).toBe('recording')

      // Simulate swipe up cancel (call cancelRecording directly)
      act(() => {
        result.current.cancelRecording()
      })

      expect(mockRecorder.stop).toHaveBeenCalled()
      expect(result.current.state).toBe('idle')
      expect(onTranscript).not.toHaveBeenCalled()
    })
  })
})
