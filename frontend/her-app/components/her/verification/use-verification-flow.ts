'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  createLiveVideoChallenge,
  isLiveVideoChallengeExpired,
  listVerificationNotifications,
  listVerificationSubmissions,
  submitLiveVideoVerification,
  type LiveVideoChallenge,
  type VerificationNotification,
  type VerificationSubmission,
} from '@/lib/api/endpoints/verification'
import {
  listFieldVerifications,
  resolveDeclaredValueFromProfile,
  submitFieldVerification,
  type FieldVerificationSubmission,
} from '@/lib/api/endpoints/field-verification'
import { fetchProfileFacts } from '@/lib/api/endpoints/collected'
import {
  startVideoRecordingSession,
  startUserFacingCamera,
  stopMediaStream,
  type RecordedVideo,
  type VideoRecordingSession,
} from '@/lib/media/video-recorder'
import { notifyError, notifySuccess } from '@/lib/notify'
import { getUserId, getProfileId } from '@/lib/auth/session'
import { getErrorMessage } from '@/lib/api/errors'
import { getSSEServerUrl } from '@/lib/sse'
import { useVerificationCacheInvalidation } from '@/lib/hooks/use-verification-cache-invalidation'
import { buildGuideSteps, getRecordingDurationSeconds } from './verification-helpers'

// SSE服务器URL
const SSE_SERVER_URL = getSSEServerUrl()

export type VerificationStep = 'video-intro' | 'video-record' | 'video-review' | 'video-pending' | 'field-upload' | 'field-pending'

export type FieldItem = {
  id: string
  name: string
  description: string
  status: 'verified' | 'pending' | 'action_required' | 'unverified'
}

const DEFAULT_FIELDS: FieldItem[] = [
  { id: 'education', name: '学历认证', description: '提供学位证书或学信网截图', status: 'unverified' },
  { id: 'occupation', name: '职业认证', description: '提供在职证明或工牌照片', status: 'unverified' },
  { id: 'income', name: '收入认证', description: '提供近三个月银行流水', status: 'unverified' },
  { id: 'video', name: '身份认证', description: '录制真人视频确保真实性', status: 'unverified' },
]

function mapSubmissionStatus(status?: string): FieldItem['status'] {
  const text = (status || '').toLowerCase()
  if (['approved', 'verified', 'completed'].includes(text)) return 'verified'
  if (['submitted', 'under_review'].includes(text)) return 'pending'
  if (['awaiting_submission', 'resubmission_required', 'rejected', 'expired'].includes(text)) return 'action_required'
  return 'unverified'
}

const API_TO_UI_FIELD: Record<string, string> = {
  education: 'education',
  job: 'occupation',
  income: 'income',
}

function mapApiFieldToUi(fieldKey?: string): string | undefined {
  if (!fieldKey) return undefined
  const direct = API_TO_UI_FIELD[fieldKey]
  if (direct) return direct
  if (fieldKey === 'occupation') return 'occupation'
  return Object.entries(API_TO_UI_FIELD).find(([, ui]) => ui === fieldKey)?.[1] || fieldKey
}

function resolveInitialStep(target: string | null): VerificationStep {
  if (target === 'education' || target === 'occupation' || target === 'income') return 'field-upload'
  return 'video-intro'
}

function hasViewableVerificationStatus(status?: string): boolean {
  const text = String(status || '').toLowerCase()
  return [
    'submitted',
    'under_review',
    'approved',
    'rejected',
    'resubmission_required',
    'expired',
    'awaiting_submission',
  ].includes(text)
}

export function useVerificationFlow(onBack: () => void) {
  console.log('[useVerificationFlow] 开始初始化')

  // 缓存失效工具
  const { invalidateAllVerificationCache } = useVerificationCacheInvalidation()

  const searchParams = useSearchParams()
  const initialTarget = searchParams.get('target')

  console.log('[useVerificationFlow] searchParams:', {
    target: initialTarget,
    from: searchParams.get('from'),
  })

  const [fieldVerificationTypes, setFieldVerificationTypes] = useState<FieldItem[]>(DEFAULT_FIELDS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [step, setStep] = useState<VerificationStep>(() => {
    const resolved = resolveInitialStep(initialTarget)
    console.log('[useVerificationFlow] resolveInitialStep 结果:', resolved)
    return resolved
  })
  const [selectedField] = useState<string | null>(() =>
    initialTarget === 'education' || initialTarget === 'occupation' || initialTarget === 'income' ? initialTarget : null,
  )
  const [isRecording, setIsRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [liveChallenge, setLiveChallenge] = useState<LiveVideoChallenge | null>(null)
  const [recordedVideo, setRecordedVideo] = useState<RecordedVideo | null>(null)
  const [currentGuideStepIndex, setCurrentGuideStepIndex] = useState(0)
  const [detectedActionEvents, setDetectedActionEvents] = useState<
    Array<{ action: string; step_index: number; detected_at_ms: number; score: number }>
  >([])
  const [spokenTranscript, setSpokenTranscript] = useState('')
  const [isSubmittingVideo, setIsSubmittingVideo] = useState(false)
  const [previewStream, setPreviewStream] = useState<MediaStream | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isSubmittingField, setIsSubmittingField] = useState(false)
  const [latestVideoSubmission, setLatestVideoSubmission] = useState<VerificationSubmission | null>(null)
  const [latestVerificationNotification, setLatestVerificationNotification] = useState<VerificationNotification | null>(null)
  const [latestFieldSubmission, setLatestFieldSubmission] = useState<FieldVerificationSubmission | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sseEventSourceRef = useRef<EventSource | null>(null)
  const sseReconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const recordingSessionRef = useRef<VideoRecordingSession | null>(null)
  const recordingTimerRef = useRef<number | null>(null)
  const recordingStartAtRef = useRef(0)
  const recordingCompletedRef = useRef(false)
  const hasResolvedInitialRouteRef = useRef(false)

  function syncVerificationState(params: {
    submissions: VerificationSubmission[]
    notifications: VerificationNotification[]
    fieldSubmissions: FieldVerificationSubmission[]
  }) {
    const latest = params.submissions[0] || null
    const latestNotification = params.notifications[0] || null
    const videoStatus = mapSubmissionStatus(latest?.status)
    const pendingHint =
      params.notifications.find((n) => n.type?.includes('resubmission'))?.body ||
      latest?.recommended_next_step ||
      latestNotification?.body ||
      '按提示完成身份认证'

    const fieldStatusByUi = new Map<string, FieldItem['status']>()
    const latestFieldSubmissionForSelected =
      selectedField
        ? params.fieldSubmissions.find((submission) => mapApiFieldToUi(submission.field_key) === selectedField) || null
        : params.fieldSubmissions[0] || null

    for (const submission of params.fieldSubmissions) {
      const uiField = mapApiFieldToUi(submission.field_key)
      if (uiField) fieldStatusByUi.set(uiField, mapSubmissionStatus(submission.status))
    }

    setLatestVideoSubmission(latest)
    setLatestVerificationNotification(latestNotification)
    setLatestFieldSubmission(latestFieldSubmissionForSelected)
    setFieldVerificationTypes(
      DEFAULT_FIELDS.map((item) => {
        if (item.id === 'video') {
          return {
            ...item,
            status: videoStatus,
            description:
              videoStatus === 'pending'
                ? pendingHint
                : videoStatus === 'action_required'
                  ? pendingHint || '认证未通过，请根据提示重新提交材料'
                  : item.description,
          }
        }
        const fieldStatus = fieldStatusByUi.get(item.id)
        return fieldStatus ? { ...item, status: fieldStatus } : item
      }),
    )

    if (!hasResolvedInitialRouteRef.current && initialTarget) {
      if (initialTarget === 'video') {
        setStep(hasViewableVerificationStatus(latest?.status) ? 'video-pending' : 'video-intro')
      } else if (selectedField) {
        setStep(hasViewableVerificationStatus(latestFieldSubmissionForSelected?.status) ? 'field-pending' : 'field-upload')
      }
      hasResolvedInitialRouteRef.current = true
    }
  }

  useEffect(() => {
    console.log('[useVerificationFlow] useEffect 开始执行')

    const userId = getUserId()
    console.log('[useVerificationFlow] userId:', userId)

    if (!userId) {
      console.log('[useVerificationFlow] 用户未登录，设置 loadError')
      setLoadError('请先登录后再进行认证')
      return
    }

    let cancelled = false
    async function loadVerificationState() {
      console.log('[loadVerificationState] 开始加载认证状态')
      try {
        const [submissions, notifications, fieldSubmissions] = await Promise.all([
          listVerificationSubmissions(),
          listVerificationNotifications(),
          listFieldVerifications(),
        ])

        console.log('[loadVerificationState] API 返回数据:', {
          submissionsLength: submissions?.length,
          notificationsLength: notifications?.length,
          fieldSubmissionsLength: fieldSubmissions?.length,
        })

        if (cancelled) return
        syncVerificationState({ submissions, notifications, fieldSubmissions })

        console.log('[loadVerificationState] fieldVerificationTypes 已更新')
        setLoadError(null)
      } catch (error) {
        if (cancelled) return
        console.error('[loadVerificationState] 加载失败:', error)
        setLoadError(getErrorMessage(error, '认证状态加载失败'))
      }
    }

    void loadVerificationState()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function ensurePreview() {
      if (step !== 'video-record' || previewStream) return
      try {
        const stream = await startUserFacingCamera()
        if (cancelled) {
          stopMediaStream(stream)
          return
        }
        setPreviewStream(stream)
      } catch (error) {
        if (!cancelled) {
          notifyError(error, '无法打开摄像头')
        }
      }
    }

    void ensurePreview()

    if (step !== 'video-record' && previewStream) {
      stopMediaStream(previewStream)
      setPreviewStream(null)
    }

    return () => {
      cancelled = true
    }
  }, [previewStream, step])

  useEffect(() => {
    return () => {
      stopMediaStream(previewStream)
      recordingSessionRef.current?.stop()
      if (recordingTimerRef.current !== null) {
        window.clearInterval(recordingTimerRef.current)
      }
    }
  }, [previewStream])

  // ✅ 新增：SSE监听验证状态变化
  useEffect(() => {
    const profileId = getProfileId()
    if (!profileId) return

    const connectSSE = () => {
      sseEventSourceRef.current = new EventSource(`${SSE_SERVER_URL}/sse/profile/${profileId}`)

      sseEventSourceRef.current.addEventListener('message', (e) => {
        try {
          const event = JSON.parse(e.data)

          // 监听验证状态变化事件
          if (event.type === 'verification_passed' || event.type === 'verification_failed') {
            console.log('[Verification SSE] 收到验证状态变化', event.type, event.message)

            // 重新加载验证状态
            async function reloadState() {
              const userId = getUserId()
              if (!userId) return

              try {
                const [submissions, notifications, fieldSubmissions] = await Promise.all([
                  listVerificationSubmissions(),
                  listVerificationNotifications(),
                  listFieldVerifications(),
                ])
                syncVerificationState({ submissions, notifications, fieldSubmissions })
                setLoadError(null)
              } catch (error) {
                setLoadError(getErrorMessage(error, '认证状态加载失败'))
              }
            }

            void reloadState()

            // 显示通知
            if (event.type === 'verification_passed') {
              notifySuccess(event.message || '恭喜！您的身份验证已通过')
            } else {
              notifyError(new Error(event.message || '验证未通过，请重新提交材料'))
            }
          }
        } catch (err) {
          console.error('[Verification SSE] 解析事件失败', err)
        }
      })

      sseEventSourceRef.current.onerror = () => {
        console.error('[Verification SSE] 连接错误')
        if (sseEventSourceRef.current) {
          sseEventSourceRef.current.close()
        }
        // 3秒后重连
        sseReconnectTimeoutRef.current = setTimeout(connectSSE, 3000)
      }
    }

    connectSSE()

    return () => {
      if (sseEventSourceRef.current) {
        sseEventSourceRef.current.close()
      }
      if (sseReconnectTimeoutRef.current) {
        clearTimeout(sseReconnectTimeoutRef.current)
      }
    }
  }, [])

  const startVideoVerification = async () => {
    setIsSubmittingVideo(true)
    try {
      const challenge = await createLiveVideoChallenge()
      setLiveChallenge(challenge)
      setLatestVideoSubmission(null)
      setLatestVerificationNotification(null)
      setCurrentGuideStepIndex(0)
      setDetectedActionEvents([])
      setSpokenTranscript('')
      setStep('video-record')
    } catch (error) {
      notifyError(error, '无法创建认证挑战')
    } finally {
      setIsSubmittingVideo(false)
    }
  }

  const handleRecordVideo = async () => {
    const recordingDurationSeconds = getRecordingDurationSeconds(liveChallenge)
    const recordingDurationMs = recordingDurationSeconds * 1000

    setIsRecording(true)
    setRecordingTime(0)
    setCurrentGuideStepIndex(0)
    setDetectedActionEvents([])
    setSpokenTranscript('')
    recordingCompletedRef.current = false
    recordingStartAtRef.current = Date.now()
    recordingTimerRef.current = window.setInterval(() => {
      setRecordingTime(Math.floor((Date.now() - recordingStartAtRef.current) / 1000))
    }, 200)

    try {
      const session = previewStream
        ? startVideoRecordingSession(previewStream, recordingDurationMs, false)
        : startVideoRecordingSession(await startUserFacingCamera(), recordingDurationMs, true)

      recordingSessionRef.current = session
      const video = await session.result
      recordingSessionRef.current = null

      if (!recordingCompletedRef.current) {
        URL.revokeObjectURL(video.blobUrl)
        setCurrentGuideStepIndex(0)
        setDetectedActionEvents([])
        setSpokenTranscript('')
        notifyError(new Error('未完成全部动作，请重新录制'))
        return
      }

      setRecordedVideo(video)
      stopMediaStream(previewStream)
      setPreviewStream(null)
      setStep('video-review')
    } catch (error) {
      notifyError(error, '录制失败')
    } finally {
      if (recordingTimerRef.current !== null) {
        window.clearInterval(recordingTimerRef.current)
        recordingTimerRef.current = null
      }
      setIsRecording(false)
    }
  }

  const completeVideoGuideStep = useCallback((params?: { score?: number; transcript?: string }) => {
    const builtSteps = buildGuideSteps(liveChallenge)
    const currentStep = builtSteps[currentGuideStepIndex]
    if (!currentStep) return

    if (currentStep.kind === 'action' && currentStep.actionKey) {
      const detectedAtMs = Math.max(0, Date.now() - recordingStartAtRef.current)
      setDetectedActionEvents((prev) => [
        ...prev,
        {
          action: currentStep.actionKey!,
          step_index: currentGuideStepIndex + 1,
          detected_at_ms: detectedAtMs,
          score: Math.round((params?.score ?? 1) * 100),
        },
      ])
    }

    if (currentStep.kind === 'spoken_code' && params?.transcript) {
      setSpokenTranscript(params.transcript)
    }

      const nextIndex = currentGuideStepIndex + 1
    if (nextIndex >= builtSteps.length) {
      recordingCompletedRef.current = true
      recordingSessionRef.current?.stop()
      return
    }

    setCurrentGuideStepIndex(nextIndex)
  }, [currentGuideStepIndex, liveChallenge])

  const finishVideoSubmission = async () => {
    const token = liveChallenge?.challenge_token
    if (!token) {
      notifyError(new Error('缺少 challenge_token，请返回重试'))
      setStep('video-intro')
      return
    }
    if (isLiveVideoChallengeExpired(liveChallenge)) {
      notifyError(new Error('本次认证已超时，请重新开始录制'))
      setLiveChallenge(null)
      setRecordedVideo(null)
      setStep('video-intro')
      return
    }
    setIsSubmittingVideo(true)
    try {
      const result = await submitLiveVideoVerification({
        challengeToken: token,
        challengePhrase: liveChallenge?.challenge_phrase,
        requiredActions: liveChallenge?.required_actions,
        videoBase64: recordedVideo?.base64,
        videoBlob: recordedVideo?.blob,
        fileName: 'verification-recording.webm',
        contentType: recordedVideo?.mimeType,
        recordingDurationMs: getRecordingDurationSeconds(liveChallenge) * 1000,
        actionEvents: detectedActionEvents,
        speechChallengeResult: spokenTranscript
          ? {
              provider: 'browser_speech_recognition',
              transcript_text: spokenTranscript,
              matched: spokenTranscript.includes(String(liveChallenge?.spoken_code || '')),
            }
          : undefined,
      })
      notifySuccess('身份认证视频已提交，等待审核')

      // ✅ 失效认证相关缓存，触发 profile 页面自动刷新
      await invalidateAllVerificationCache()

      setLatestVideoSubmission(result.submission || null)
      setLatestVerificationNotification(null)
      setStep('video-pending')
    } catch (error) {
      const message = getErrorMessage(error, '视频提交失败')
      if (message.includes('challenge_token has expired')) {
        notifyError(new Error('本次认证已超时，请重新开始录制'))
        setLiveChallenge(null)
        setRecordedVideo(null)
        setStep('video-intro')
      } else {
        notifyError(error, '视频提交失败')
        setStep('video-review')
      }
    } finally {
      setIsSubmittingVideo(false)
    }
  }

  const handleSubmitField = async () => {
    if (!selectedField) return
    const fieldKey = selectedField as 'education' | 'occupation' | 'income'
    if (!selectedFile) {
      notifyError(new Error('请先选择要上传的文件'))
      return
    }
    setIsSubmittingField(true)
    try {
      const profileFactsResponse = await fetchProfileFacts()
      const declaredValue = resolveDeclaredValueFromProfile(
        profileFactsResponse.profile_facts || {},
        fieldKey,
      )

      const result = await submitFieldVerification({
        fieldId: fieldKey,
        file: selectedFile,
        declaredValue,
      })
      notifySuccess('材料已提交，等待审核')

      // ✅ 失效认证相关缓存，触发 profile 页面自动刷新
      await invalidateAllVerificationCache()

      setLatestFieldSubmission(result.submission || null)
      setStep('field-pending')
    } catch (error) {
      notifyError(error, '材料提交失败')
    } finally {
      setIsSubmittingField(false)
    }
  }

  return {
    fieldVerificationTypes,
    loadError,
    step,
    setStep,
    selectedField,
    isRecording,
    recordingTime,
    liveChallenge,
    latestVideoSubmission,
    latestVerificationNotification,
    latestFieldSubmission,
    recordedVideo,
    currentGuideStepIndex,
    previewStream,
    setRecordedVideo,
    isSubmittingVideo,
    selectedFile,
    setSelectedFile,
    isSubmittingField,
    fileInputRef,
    handleDirectBack: onBack,
    startVideoVerification,
    handleRecordVideo,
    completeVideoGuideStep,
    finishVideoSubmission,
    handleSubmitField,
  }
}
