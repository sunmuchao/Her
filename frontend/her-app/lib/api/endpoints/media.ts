/**
 * 媒体上传 API
 */

import { gatewayJson } from '@/lib/api/client'

export type MediaType = 'image'

export type MediaMetadata = {
  width?: number
  height?: number
  size: number // bytes
  mimeType: string
}

export type UploadMediaResponse = {
  mediaId: string
  mediaUrl: string
  mediaType: MediaType
  metadata: MediaMetadata
}

/**
 * 上传图片到 MinIO
 */
export async function uploadImage(
  file: File,
): Promise<UploadMediaResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('media_type', 'image')

  // 获取访问令牌
  const accessToken = typeof window !== 'undefined'
    ? document.cookie.split('; ').find(row => row.startsWith('her_access_token='))?.split('=')[1]
    : null

  const headers = new Headers()
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const response = await fetch('/api/gateway/v2/media/upload', {
    method: 'POST',
    headers,
    body: formData,
    credentials: 'include',
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`上传失败: ${errorText}`)
  }

  return response.json()
}

/**
 * 压缩图片（如果超过 1MB）
 */
export async function compressImage(
  file: File,
  maxWidth = 1920,
  maxHeight = 1920,
  quality = 0.8,
): Promise<File> {
  // 如果文件小于 500KB，不压缩
  if (file.size < 500 * 1024) {
    return file
  }

  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      let { width, height } = img

      // 计算缩放比例
      if (width > maxWidth) {
        height = (height * maxWidth) / width
        width = maxWidth
      }
      if (height > maxHeight) {
        width = (width * maxHeight) / height
        height = maxHeight
      }

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height

      const ctx = canvas.getContext('2d')
      if (!ctx) {
        reject(new Error('无法创建 Canvas'))
        return
      }

      ctx.drawImage(img, 0, 0, width, height)

      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error('压缩失败'))
            return
          }
          // 创建新的 File 对象
          const compressedFile = new File([blob], file.name, {
            type: file.type,
            lastModified: Date.now(),
          })
          resolve(compressedFile)
        },
        file.type,
        quality,
      )
    }

    img.onerror = () => reject(new Error('图片加载失败'))
    img.src = URL.createObjectURL(file)
  })
}

/**
 * 获取图片预览 URL
 */
export function getImagePreviewUrl(file: File): string {
  return URL.createObjectURL(file)
}