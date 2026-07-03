'use client'

import { useEffect, useRef, useState, type RefObject } from 'react'

const FACE_LANDMARKER_WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm'
const FACE_LANDMARKER_MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

type FaceLandmarkerClass = {
  createFromOptions: (fileset: unknown, options: Record<string, unknown>) => Promise<FaceLandmarkerInstance>
}

type FaceLandmarkerInstance = {
  detectForVideo: (videoFrame: HTMLVideoElement, timestamp: number) => FaceLandmarkerResult
}

type FilesetResolverClass = {
  forVisionTasks: (wasmPath: string) => Promise<unknown>
}

type FaceLandmarkerResult = {
  faceLandmarks: Array<Array<{ x: number; y: number; z?: number }>>
  faceBlendshapes?: Array<{
    categories?: Array<{
      categoryName: string
      score: number
    }>
  }>
}

type MediaPipeVisionModule = {
  FaceLandmarker: FaceLandmarkerClass
  FilesetResolver: FilesetResolverClass
}

type SupportedAction = 'blink' | 'open_mouth' | 'turn_left' | 'turn_right' | 'nod_up'

type DetectionHit = {
  detected: boolean
  score: number
}

type UseLiveFaceChallengeParams = {
  videoRef: RefObject<HTMLVideoElement | null>
  enabled: boolean
  expectedAction?: string
  onActionDetected: (score: number) => void
}

type UseLiveFaceChallengeResult = {
  isReady: boolean
  statusText: string
}

let faceLandmarkerPromise: Promise<FaceLandmarkerInstance> | null = null

async function loadMediaPipeVisionModule(): Promise<MediaPipeVisionModule> {
  return import(
    /* webpackIgnore: true */
    'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/vision_bundle.mjs'
  ) as Promise<MediaPipeVisionModule>
}

async function getFaceLandmarker() {
  if (!faceLandmarkerPromise) {
    faceLandmarkerPromise = (async () => {
      const { FaceLandmarker, FilesetResolver } = await loadMediaPipeVisionModule()
      const fileset = await FilesetResolver.forVisionTasks(FACE_LANDMARKER_WASM_URL)
      return FaceLandmarker.createFromOptions(fileset, {
        baseOptions: {
          modelAssetPath: FACE_LANDMARKER_MODEL_URL,
        },
        runningMode: 'VIDEO',
        numFaces: 1,
        minFaceDetectionConfidence: 0.6,
        minFacePresenceConfidence: 0.6,
        minTrackingConfidence: 0.6,
        outputFaceBlendshapes: true,
      })
    })()
  }

  return faceLandmarkerPromise
}

function distance(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function getBlendshapeScore(result: FaceLandmarkerResult, name: string) {
  const categories = result.faceBlendshapes?.[0]?.categories || []
  const hit = categories.find((item) => item.categoryName === name)
  return hit?.score || 0
}

function canProcessVideoFrame(video: HTMLVideoElement) {
  return (
    video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
    video.videoWidth > 0 &&
    video.videoHeight > 0 &&
    Number.isFinite(video.currentTime) &&
    !video.paused &&
    !video.ended
  )
}

function detectAction(result: FaceLandmarkerResult, expectedAction: SupportedAction): DetectionHit {
  const landmarks = result.faceLandmarks?.[0]
  if (!landmarks || landmarks.length < 400) {
    return { detected: false, score: 0 }
  }

  const faceWidth = distance(landmarks[234]!, landmarks[454]!)
  const faceHeight = distance(landmarks[10]!, landmarks[152]!)
  const eyeCenter = {
    x: (landmarks[33]!.x + landmarks[263]!.x) / 2,
    y: (landmarks[33]!.y + landmarks[263]!.y) / 2,
  }
  const noseTip = landmarks[1]!
  const yawOffset = faceWidth > 0 ? (noseTip.x - eyeCenter.x) / faceWidth : 0
  const pitchOffset = faceHeight > 0 ? (eyeCenter.y - noseTip.y) / faceHeight : 0

  const leftBlinkScore = getBlendshapeScore(result, 'eyeBlinkLeft')
  const rightBlinkScore = getBlendshapeScore(result, 'eyeBlinkRight')
  const blinkScore = Math.max(leftBlinkScore, rightBlinkScore)

  const jawOpenScore = Math.max(
    getBlendshapeScore(result, 'jawOpen'),
    getBlendshapeScore(result, 'mouthOpen'),
  )
  const mouthRatio =
    faceWidth > 0 ? distance(landmarks[13]!, landmarks[14]!) / distance(landmarks[78]!, landmarks[308]!) : 0
  const mouthOpenScore = Math.max(jawOpenScore, Math.min(1, mouthRatio * 3.5))

  if (expectedAction === 'blink') {
    return { detected: blinkScore > 0.45, score: blinkScore }
  }

  if (expectedAction === 'open_mouth') {
    return { detected: mouthOpenScore > 0.42, score: mouthOpenScore }
  }

  if (expectedAction === 'turn_left') {
    const score = Math.min(1, Math.max(0, (yawOffset - 0.03) / 0.06))
    return { detected: yawOffset > 0.09, score }
  }

  if (expectedAction === 'turn_right') {
    const score = Math.min(1, Math.max(0, (-yawOffset - 0.03) / 0.06))
    return { detected: yawOffset < -0.09, score }
  }

  const score = Math.min(1, Math.max(0, (pitchOffset - 0.14) / 0.08))
  return { detected: pitchOffset > 0.22, score }
}

export function useLiveFaceChallenge({
  videoRef,
  enabled,
  expectedAction,
  onActionDetected,
}: UseLiveFaceChallengeParams): UseLiveFaceChallengeResult {
  const [isReady, setIsReady] = useState(false)
  const [statusText, setStatusText] = useState('正在加载动作识别...')
  const frameRef = useRef<number | null>(null)
  const stableCountRef = useRef(0)
  const lastStepKeyRef = useRef<string>('')
  const onActionDetectedRef = useRef(onActionDetected)

  useEffect(() => {
    onActionDetectedRef.current = onActionDetected
  }, [onActionDetected])

  useEffect(() => {
    let cancelled = false

    if (!enabled || !expectedAction) {
      setStatusText('')
      stableCountRef.current = 0
      return
    }

    const supportedAction = expectedAction as SupportedAction
    const video = videoRef.current

    if (!video) {
      setStatusText('正在准备摄像头...')
      return
    }

    if (lastStepKeyRef.current !== supportedAction) {
      lastStepKeyRef.current = supportedAction
      stableCountRef.current = 0
    }

    async function start() {
      try {
        const landmarker = await getFaceLandmarker()
        if (cancelled) return

        const scheduleNextLoop = () => {
          frameRef.current = window.setTimeout(loop, 120) as unknown as number
        }

        const loop = () => {
          if (cancelled) return
          const node = videoRef.current
          if (!node || !canProcessVideoFrame(node)) {
            frameRef.current = window.requestAnimationFrame(loop)
            return
          }

          try {
            const result = landmarker.detectForVideo(node, performance.now())
            const hit = detectAction(result, supportedAction)

            setIsReady(true)
            setStatusText('识别中...')

            if (hit.detected) {
              stableCountRef.current += 1
            } else {
              stableCountRef.current = 0
            }

            const requiredStableFrames = supportedAction === 'blink' ? 1 : 2
            if (stableCountRef.current >= requiredStableFrames) {
              stableCountRef.current = 0
              onActionDetectedRef.current(hit.score)
              return
            }
          } catch (error) {
            stableCountRef.current = 0
            if (!cancelled) {
              console.warn('[useLiveFaceChallenge] detectForVideo failed, retrying', error)
              setStatusText('正在调整识别...')
            }
          }

          scheduleNextLoop()
        }

        loop()
      } catch (error) {
        console.error('[useLiveFaceChallenge] 动作识别初始化失败', error)
        if (!cancelled) {
          setStatusText('动作识别不可用')
        }
      }
    }

    void start()

    return () => {
      cancelled = true
      if (frameRef.current !== null) {
        window.clearTimeout(frameRef.current)
        window.cancelAnimationFrame(frameRef.current)
        frameRef.current = null
      }
    }
  }, [enabled, expectedAction, videoRef])

  return {
    isReady,
    statusText,
  }
}
