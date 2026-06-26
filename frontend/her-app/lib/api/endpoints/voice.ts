import { gatewayJson } from '@/lib/api/client'

/**
 * 语音识别 API - 使用后端 Whisper 模型
 */

export interface VoiceTranscriptionResult {
  success: boolean
  text: string
  language: string
  language_probability: number
  segments: Array<{
    start: number
    end: number
    text: string
  }>
}

/**
 * 发送音频文件到后端进行语音识别
 * @param audioBlob - 录制的音频 Blob（webm/mp4 格式）
 * @returns 识别结果
 */
export async function transcribeVoice(audioBlob: Blob): Promise<VoiceTranscriptionResult> {
  // 直接发送 audio blob 到 gateway
  const response = await fetch('/api/gateway/v1/voice/transcribe', {
    method: 'POST',
    body: audioBlob,
    headers: {
      'Content-Type': audioBlob.type || 'audio/webm',
    },
  })

  if (!response.ok) {
    const errorData = await response.json()
    throw new Error(errorData.error?.message || '语音识别失败')
  }

  return response.json()
}