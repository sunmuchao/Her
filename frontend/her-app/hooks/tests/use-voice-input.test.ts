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

  describe('recording duration tracking', () => {
    it('should track recording duration correctly', async () => {
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

      expect(result.current.recordingDuration).toBe(0)

      await act(async () => {
        await result.current.startRecording()
      })

      // Wait for timer to increment
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 150))
      })

      expect(result.current.recordingDuration).toBeGreaterThan(0)
    })

    it('should reset recording duration when recording stops', async () => {
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

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 150))
      })

      expect(result.current.recordingDuration).toBeGreaterThan(0)

      act(() => {
        result.current.stopRecording()
      })

      // Duration should be reset in cleanup (after onstop)
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      expect(result.current.recordingDuration).toBe(0)
    })
  })
})
