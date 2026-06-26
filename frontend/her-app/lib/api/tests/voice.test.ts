/**
 * Unit tests for voice API endpoint functions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { transcribeVoice } from '../endpoints/voice'

// Mock fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
})

describe('voice API endpoints', () => {
  describe('transcribeVoice', () => {
    it('should send audio blob to Whisper API and return result', async () => {
      const audioBlob = new Blob(['audio data'], { type: 'audio/webm' })

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          text: '测试语音识别文本',
          language: 'zh',
          language_probability: 0.98,
          segments: [
            {
              start: 0.0,
              end: 2.5,
              text: '测试语音识别文本',
            },
          ],
        }),
      })

      const result = await transcribeVoice(audioBlob)

      expect(mockFetch).toHaveBeenCalledWith('/api/gateway/v1/voice/transcribe', {
        method: 'POST',
        body: audioBlob,
        headers: {
          'Content-Type': 'audio/webm',
        },
      })

      expect(result.success).toBe(true)
      expect(result.text).toBe('测试语音识别文本')
      expect(result.language).toBe('zh')
      expect(result.language_probability).toBe(0.98)
      expect(result.segments).toHaveLength(1)
    })

    it('should handle API errors gracefully', async () => {
      const audioBlob = new Blob(['audio data'], { type: 'audio/webm' })

      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({
          error: {
            code: 'transcription_failed',
            message: 'Whisper model crashed',
          },
        }),
      })

      await expect(transcribeVoice(audioBlob)).rejects.toThrow('Whisper model crashed')
    })

    it('should handle network errors', async () => {
      const audioBlob = new Blob(['audio data'], { type: 'audio/webm' })

      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      await expect(transcribeVoice(audioBlob)).rejects.toThrow('Network error')
    })

    it('should use audio/webm as default content type', async () => {
      const audioBlob = new Blob(['audio data']) // No type specified

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          text: 'test',
          language: 'zh',
          language_probability: 0.5,
          segments: [],
        }),
      })

      await transcribeVoice(audioBlob)

      expect(mockFetch).toHaveBeenCalledWith('/api/gateway/v1/voice/transcribe', {
        method: 'POST',
        body: audioBlob,
        headers: {
          'Content-Type': 'audio/webm',
        },
      })
    })

    it('should use audio/mp4 content type for mp4 blobs', async () => {
      const audioBlob = new Blob(['audio data'], { type: 'audio/mp4' })

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          text: 'test',
          language: 'zh',
          language_probability: 0.5,
          segments: [],
        }),
      })

      await transcribeVoice(audioBlob)

      expect(mockFetch).toHaveBeenCalledWith('/api/gateway/v1/voice/transcribe', {
        method: 'POST',
        body: audioBlob,
        headers: {
          'Content-Type': 'audio/mp4',
        },
      })
    })
  })
})