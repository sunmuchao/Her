export type RecordedVideo = {
  blob: Blob
  blobUrl: string
  base64: string
  mimeType: string
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('无法读取视频数据'))
        return
      }
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(reader.error ?? new Error('读取视频失败'))
    reader.readAsDataURL(blob)
  })
}

export async function recordVideoFromCamera(maxDurationMs = 6000): Promise<RecordedVideo> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('当前环境不支持摄像头录制')
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: 'user' },
    audio: true,
  })

  const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
    ? 'video/webm;codecs=vp9'
    : MediaRecorder.isTypeSupported('video/webm')
      ? 'video/webm'
      : ''

  const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
  const chunks: BlobPart[] = []

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data)
  }

  const recorded = new Promise<Blob>((resolve, reject) => {
    recorder.onerror = () => reject(new Error('录制失败'))
    recorder.onstop = () => {
      resolve(new Blob(chunks, { type: recorder.mimeType || 'video/webm' }))
    }
  })

  recorder.start(250)

  await new Promise<void>((resolve) => {
    setTimeout(resolve, maxDurationMs)
  })

  if (recorder.state !== 'inactive') {
    recorder.stop()
  }

  stream.getTracks().forEach((track) => track.stop())

  const blob = await recorded
  const base64 = await blobToBase64(blob)
  const blobUrl = URL.createObjectURL(blob)

  return {
    blob,
    blobUrl,
    base64,
    mimeType: blob.type || 'video/webm',
  }
}
