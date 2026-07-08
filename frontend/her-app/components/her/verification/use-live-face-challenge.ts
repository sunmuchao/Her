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
let lastTimestamp = 0

function getMonotonicTimestamp(): number {
  const now = performance.now()
  // Ensure timestamp is strictly monotonic (VIDEO runningMode requirement)
  lastTimestamp = Math.max(now, lastTimestamp + 0.001)
  return lastTimestamp
}

async function loadMediaPipeVisionModule(): Promise<MediaPipeVisionModule> {
  return import(
    // @ts-expect-error - dynamic import of external module without type declarations
    /* webpackIgnore: true */ 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/vision_bundle.mjs'
  ) as Promise<MediaPipeVisionModule>
}

async function getFaceLandmarker() {
  if (!faceLandmarkerPromise) {
    console.log('[useLiveFaceChallenge] Initializing FaceLandmarker...')
    faceLandmarkerPromise = (async () => {
      try {
        console.log('[useLiveFaceChallenge] Loading MediaPipe Vision Module...')
        const { FaceLandmarker, FilesetResolver } = await loadMediaPipeVisionModule()
        console.log('[useLiveFaceChallenge] MediaPipe Vision Module loaded')

        console.log('[useLiveFaceChallenge] Creating FilesetResolver...')
        const fileset = await FilesetResolver.forVisionTasks(FACE_LANDMARKER_WASM_URL)
        console.log('[useLiveFaceChallenge] FilesetResolver created')

        console.log('[useLiveFaceChallenge] Creating FaceLandmarker instance...')
        console.log('[useLiveFaceChallenge] Creating with options:', {
          runningMode: 'VIDEO',
          numFaces: 1,
          minFaceDetectionConfidence: 0.6,
          minFacePresenceConfidence: 0.6,
          minTrackingConfidence: 0.6,
          outputFaceBlendshapes: true,
          modelAssetPath: FACE_LANDMARKER_MODEL_URL,
        })

        const landmarker = await FaceLandmarker.createFromOptions(fileset, {
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

        console.log('[useLiveFaceChallenge] FaceLandmarker.createFromOptions() returned')
        console.log('[useLiveFaceChallenge] Landmarker type:', typeof landmarker)
        console.log('[useLiveFaceChallenge] Landmarker methods:', landmarker ? Object.keys(landmarker) : 'null')
        console.log('[useLiveFaceChallenge] FaceLandmarker instance created successfully')
        return landmarker
      } catch (initError) {
        console.error('[useLiveFaceChallenge] Failed to initialize FaceLandmarker', initError)
        // Reset promise to allow retry
        faceLandmarkerPromise = null
        throw initError
      }
    })()
  }

  return faceLandmarkerPromise
}

/**
 * Reset the global face landmarker instance (use for recovery after severe errors)
 */
function resetFaceLandmarker() {
  faceLandmarkerPromise = null
  lastTimestamp = 0
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

function assertVideoReadyForDetection(video: HTMLVideoElement): boolean {
  if (!canProcessVideoFrame(video)) {
    return false
  }
  // Additional safety checks
  if (video.videoWidth < 64 || video.videoHeight < 64) {
    return false
  }
  if (!Number.isFinite(video.currentTime) || video.currentTime < 0) {
    return false
  }
  return true
}

function detectAction(result: FaceLandmarkerResult, expectedAction: SupportedAction): DetectionHit {
  const landmarks = result.faceLandmarks?.[0]
  if (!landmarks || landmarks.length < 400) {
    console.warn('[useLiveFaceChallenge] No face landmarks detected', {
      hasLandmarks: !!landmarks,
      landmarkCount: landmarks?.length || 0,
    })
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

  // Debug: log all blendshapes available
  const availableBlendshapes = result.faceBlendshapes?.[0]?.categories?.map(c => c.categoryName) || []
  console.log('[useLiveFaceChallenge] All blendshapes available', availableBlendshapes)

  if (expectedAction === 'blink') {
    console.log('[useLiveFaceChallenge] blink detection', {
      leftBlinkScore,
      rightBlinkScore,
      finalScore: blinkScore,
      threshold: 0.45,
      detected: blinkScore > 0.45,
    })
    return { detected: blinkScore > 0.45, score: blinkScore }
  }

  if (expectedAction === 'open_mouth') {
    console.log('[useLiveFaceChallenge] open_mouth detection', {
      jawOpenScore: getBlendshapeScore(result, 'jawOpen'),
      mouthOpenScore: getBlendshapeScore(result, 'mouthOpen'),
      mouthRatio,
      finalScore: mouthOpenScore,
      threshold: 0.42,
      detected: mouthOpenScore > 0.42,
    })
    return { detected: mouthOpenScore > 0.42, score: mouthOpenScore }
  }

  if (expectedAction === 'turn_left') {
    const score = Math.min(1, Math.max(0, (yawOffset - 0.03) / 0.06))
    console.log('[useLiveFaceChallenge] turn_left detection', {
      yawOffset,
      finalScore: score,
      threshold: 0.09,
      detected: yawOffset > 0.09,
    })
    return { detected: yawOffset > 0.09, score }
  }

  if (expectedAction === 'turn_right') {
    const score = Math.min(1, Math.max(0, (-yawOffset - 0.03) / 0.06))
    console.log('[useLiveFaceChallenge] turn_right detection', {
      yawOffset,
      finalScore: score,
      threshold: -0.09,
      detected: yawOffset < -0.09,
    })
    return { detected: yawOffset < -0.09, score }
  }

  // nod_up
  const score = Math.min(1, Math.max(0, (pitchOffset - 0.14) / 0.08))
  console.log('[useLiveFaceChallenge] nod_up detection', {
    pitchOffset,
    finalScore: score,
    threshold: 0.22,
    detected: pitchOffset > 0.22,
  })
  return { detected: pitchOffset > 0.22, score }
}

type FrameSchedule = {
  type: 'timeout' | 'raf'
  id: number
}

export function useLiveFaceChallenge({
  videoRef,
  enabled,
  expectedAction,
  onActionDetected,
}: UseLiveFaceChallengeParams): UseLiveFaceChallengeResult {
  const [isReady, setIsReady] = useState(false)
  const [statusText, setStatusText] = useState('正在加载动作识别...')
  const frameRef = useRef<FrameSchedule | null>(null)
  const stableCountRef = useRef(0)
  const lastStepKeyRef = useRef<string>('')
  const errorCountRef = useRef(0)
  const onActionDetectedRef = useRef(onActionDetected)

  useEffect(() => {
    onActionDetectedRef.current = onActionDetected
  }, [onActionDetected])

  useEffect(() => {
    let cancelled = false

    if (!enabled || !expectedAction) {
      setStatusText('')
      stableCountRef.current = 0
      errorCountRef.current = 0
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

        // Pre-flight check: verify MediaPipe is truly functional before starting loop
        console.log('[useLiveFaceChallenge] Running pre-flight check...')

        const video = videoRef.current
        if (!video) {
          console.warn('[useLiveFaceChallenge] No video element for pre-flight check')
          setStatusText('正在准备摄像头...')
          return
        }

        // Wait for video to be truly ready with a small delay
        let attempts = 0
        const maxAttempts = 10
        while (attempts < maxAttempts && !cancelled) {
          if (assertVideoReadyForDetection(video)) {
            break
          }
          attempts += 1
          console.log('[useLiveFaceChallenge] Waiting for video ready, attempt', attempts)
          await new Promise(resolve => setTimeout(resolve, 200))
        }

        if (!assertVideoReadyForDetection(video)) {
          console.error('[useLiveFaceChallenge] Video never became ready for detection')
          setStatusText('摄像头准备失败')
          return
        }

        // Try a single detectForVideo call to verify MediaPipe is functional
        try {
          const testTimestamp = getMonotonicTimestamp()
          const testResult = landmarker.detectForVideo(video, testTimestamp)
          console.log('[useLiveFaceChallenge] Pre-flight check successful', {
            hasLandmarks: !!testResult.faceLandmarks,
            landmarkCount: testResult.faceLandmarks?.[0]?.length || 0,
            hasBlendshapes: !!testResult.faceBlendshapes,
          })
        } catch (preflightError) {
          console.error('[useLiveFaceChallenge] Pre-flight check failed, MediaPipe not functional', preflightError)
          // Reset and retry once
          resetFaceLandmarker()
          setStatusText('动作识别初始化失败，请刷新页面')
          return
        }

        console.log('[useLiveFaceChallenge] Starting detection loop...')

        const scheduleRaf = () => {
          frameRef.current = { type: 'raf', id: window.requestAnimationFrame(loop) }
        }

        const scheduleTimeout = (delay: number) => {
          frameRef.current = { type: 'timeout', id: window.setTimeout(loop, delay) as unknown as number }
        }

        const loop = () => {
          if (cancelled) return
          const node = videoRef.current

          // First check: video element existence
          if (!node) {
            console.warn('[useLiveFaceChallenge] Video element not found, skipping detection')
            scheduleTimeout(200)
            return
          }

          // Second check: video stream status
          if (!node.srcObject) {
            console.warn('[useLiveFaceChallenge] No video stream attached, skipping detection')
            scheduleTimeout(200)
            return
          }

          const stream = node.srcObject as MediaStream
          const videoTracks = stream.getVideoTracks()
          if (videoTracks.length === 0) {
            console.warn('[useLiveFaceChallenge] No video tracks in stream, skipping detection')
            scheduleTimeout(200)
            return
          }

          const activeTrack = videoTracks[0]
          if (!activeTrack || activeTrack.readyState !== 'live') {
            console.warn('[useLiveFaceChallenge] Video track not live, skipping detection', {
              trackState: activeTrack?.readyState,
              trackEnabled: activeTrack?.enabled,
            })
            scheduleTimeout(200)
            return
          }

          // Third check: video element ready state (use comprehensive check)
          if (!assertVideoReadyForDetection(node)) {
            console.warn('[useLiveFaceChallenge] Video not ready for detection', {
              readyState: node.readyState,
              readyStateText: ['HAVE_NOTHING', 'HAVE_METADATA', 'HAVE_CURRENT_DATA', 'HAVE_FUTURE_DATA', 'HAVE_ENOUGH_DATA'][node.readyState] || 'UNKNOWN',
              paused: node.paused,
              ended: node.ended,
              currentTime: node.currentTime,
              width: node.videoWidth,
              height: node.videoHeight,
            })
            scheduleTimeout(200)
            return
          }

          // Fourth check: additional safety before MediaPipe call
          if (node.videoWidth < 64 || node.videoHeight < 64) {
            console.warn('[useLiveFaceChallenge] Video dimensions too small', {
              width: node.videoWidth,
              height: node.videoHeight,
            })
            scheduleTimeout(200)
            return
          }

          let timestamp = 0
          try {
            timestamp = getMonotonicTimestamp()
            const result = landmarker.detectForVideo(node, timestamp)
            const hit = detectAction(result, supportedAction)

            // Reset error counter on successful detection
            errorCountRef.current = 0

            setIsReady(true)
            setStatusText('识别中...')

            const requiredStableFrames = supportedAction === 'blink' ? 1 : 2

            if (hit.detected) {
              stableCountRef.current += 1
              console.log('[useLiveFaceChallenge] action detected', {
                action: supportedAction,
                score: hit.score,
                stableCount: stableCountRef.current,
                required: requiredStableFrames,
              })
            } else {
              stableCountRef.current = 0
            }

            if (stableCountRef.current >= requiredStableFrames) {
              stableCountRef.current = 0
              onActionDetectedRef.current(hit.score)
              return
            }
          } catch (error) {
            stableCountRef.current = 0
            errorCountRef.current += 1

            if (!cancelled) {
              // Enhanced error logging - extract all possible error information
              const errorInfo: Record<string, unknown> = {}

              if (error instanceof Error) {
                errorInfo.type = 'Error'
                errorInfo.message = error.message
                errorInfo.stack = error.stack
                errorInfo.name = error.name
              } else if (error && typeof error === 'object') {
                errorInfo.type = 'Object'
                errorInfo.rawObject = error
                // Try to extract all properties from the error object
                try {
                  const props = Object.keys(error)
                  errorInfo.properties = props
                  props.forEach(prop => {
                    try {
                      errorInfo[`prop_${prop}`] = (error as Record<string, unknown>)[prop]
                    } catch {
                      errorInfo[`prop_${prop}`] = '[ inaccessible ]'
                    }
                  })
                } catch (propError) {
                  errorInfo.propertyExtractionFailed = String(propError)
                }
                // Try JSON stringify
                try {
                  errorInfo.jsonStringify = JSON.stringify(error)
                } catch {
                  errorInfo.jsonStringify = '[ circular reference ]'
                }
              } else {
                errorInfo.type = 'Unknown'
                errorInfo.raw = String(error)
                errorInfo.rawTypeof = typeof error
              }

              // Check video stream integrity
              const stream = node.srcObject as MediaStream | null
              const videoTracks = stream?.getVideoTracks() || []
              const streamBroken = !stream || videoTracks.length === 0 || videoTracks[0]?.readyState !== 'live'

              console.error('[useLiveFaceChallenge] detectForVideo failed', {
                error: errorInfo,
                videoState: {
                  readyState: node.readyState,
                  readyStateText: ['HAVE_NOTHING', 'HAVE_METADATA', 'HAVE_CURRENT_DATA', 'HAVE_FUTURE_DATA', 'HAVE_ENOUGH_DATA'][node.readyState] || 'UNKNOWN',
                  paused: node.paused,
                  ended: node.ended,
                  currentTime: node.currentTime,
                  duration: node.duration,
                  width: node.videoWidth,
                  height: node.videoHeight,
                  srcObject: node.srcObject ? 'present' : 'null',
                  srcObjectTracks: videoTracks.length,
                  streamBroken,
                },
                timestamp,
                landmarkerState: {
                  hasLandmarker: !!landmarker,
                  landmarkerType: typeof landmarker,
                },
                consecutiveErrors: errorCountRef.current,
              })

              // Stop immediately if video stream is broken
              if (streamBroken) {
                console.error('[useLiveFaceChallenge] Video stream broken, stopping detection loop')
                setStatusText('摄像头连接中断')
                return
              }

              // Stop if too many consecutive errors
              if (errorCountRef.current >= 5) {
                console.error('[useLiveFaceChallenge] Too many consecutive errors, stopping detection loop and resetting landmarker')
                setStatusText('动作识别不可用，请刷新页面重试')
                resetFaceLandmarker()
                return
              }

              setStatusText('正在调整识别...')

              // Check for severe error patterns (including WASM-related)
              const errorStr = error instanceof Error ? error.message : String(error)
              if (errorStr.includes('tensor') ||
                  errorStr.includes('delegate') ||
                  errorStr.includes('internal') ||
                  errorStr.includes('WASM') ||
                  errorStr.includes('memory') ||
                  errorStr.includes('allocation') ||
                  (errorInfo.properties && (errorInfo.properties as string[]).includes('code'))) {
                console.error('[useLiveFaceChallenge] Severe error detected, stopping detection loop and resetting landmarker')
                setStatusText('动作识别遇到严重错误，请刷新页面')
                resetFaceLandmarker()
                return
              }
            }
          }

          scheduleTimeout(120)
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
        if (frameRef.current.type === 'timeout') {
          window.clearTimeout(frameRef.current.id)
        } else {
          window.cancelAnimationFrame(frameRef.current.id)
        }
        frameRef.current = null
      }
    }
  }, [enabled, expectedAction, videoRef])

  return {
    isReady,
    statusText,
  }
}
