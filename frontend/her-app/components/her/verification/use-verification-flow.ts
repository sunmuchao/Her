'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import {
  createLiveVideoChallenge,
  listVerificationNotifications,
  listVerificationSubmissions,
  submitLiveVideoVerification,
  type LiveVideoChallenge,
} from '@/lib/api/endpoints/verification'
import {
  listFieldVerifications,
  submitFieldVerification,
} from '@/lib/api/endpoints/field-verification'
import { recordVideoFromCamera, type RecordedVideo } from '@/lib/media/video-recorder'
import { notifyError, notifySuccess } from '@/lib/notify'
import { getUserId, getProfileId } from '@/lib/auth/session'
import { getErrorMessage } from '@/lib/api/errors'

// SSE服务器URL
const SSE_SERVER_URL = process.env.NEXT_PUBLIC_SSE_SERVER_URL || 'http://localhost:8000'

export type VerificationStep = 'video-intro' | 'video-record' | 'video-review' | 'video-pending' | 'field-upload' | 'field-pending'

export type FieldItem = {
  id: string
  name: string
  description: string
  status: 'verified' | 'pending' | 'unverified'
}

const DEFAULT_FIELDS: FieldItem[] = [
  { id: 'education', name: '学历认证', description: '提供学位证书或学信网截图', status: 'unverified' },
  { id: 'occupation', name: '职业认证', description: '提供在职证明或工牌照片', status: 'unverified' },
  { id: 'income', name: '收入认证', description: '提供近三个月银行流水', status: 'unverified' },
  { id: 'video', name: '活体视频认证', description: '录制真人视频确保真实性', status: 'unverified' },
]

function mapSubmissionStatus(status?: string): FieldItem['status'] {
  const text = (status || '').toLowerCase()
  if (['approved', 'verified', 'completed'].includes(text)) return 'verified'
  if (['submitted', 'under_review', 'awaiting_submission', 'resubmission_required'].includes(text)) return 'pending'
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

export function useVerificationFlow(onBack: () => void) {
  const searchParams = useSearchParams()
  const initialTarget = searchParams.get('target')
  const [fieldVerificationTypes, setFieldVerificationTypes] = useState<FieldItem[]>(DEFAULT_FIELDS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [step, setStep] = useState<VerificationStep>(() => resolveInitialStep(initialTarget))
  const [selectedField] = useState<string | null>(() =>
    initialTarget === 'education' || initialTarget === 'occupation' || initialTarget === 'income' ? initialTarget : null,
  )
  const [isRecording, setIsRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [liveChallenge, setLiveChallenge] = useState<LiveVideoChallenge | null>(null)
  const [recordedVideo, setRecordedVideo] = useState<RecordedVideo | null>(null)
  const [isSubmittingVideo, setIsSubmittingVideo] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isSubmittingField, setIsSubmittingField] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sseEventSourceRef = useRef<EventSource | null>(null)
  const sseReconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    const userId = getUserId()
    if (!userId) {
      setLoadError('请先登录后再进行认证')
      return
    }

    let cancelled = false
    async function loadVerificationState() {
      try {
        const [submissions, notifications, fieldSubmissions] = await Promise.all([
          listVerificationSubmissions(),
          listVerificationNotifications(),
          listFieldVerifications(),
        ])
        if (cancelled) return
        const latest = submissions[0]
        const videoStatus = mapSubmissionStatus(latest?.status)
        const pendingHint =
          notifications.find((n) => n.type?.includes('resubmission'))?.body ||
          notifications[0]?.body ||
          '按提示完成活体视频认证'

        const fieldStatusByUi = new Map<string, FieldItem['status']>()
        for (const submission of fieldSubmissions) {
          const uiField = mapApiFieldToUi(submission.field_key)
          if (uiField) fieldStatusByUi.set(uiField, mapSubmissionStatus(submission.status))
        }

        setFieldVerificationTypes(
          DEFAULT_FIELDS.map((item) => {
            if (item.id === 'video') {
              return {
                ...item,
                status: videoStatus,
                description: videoStatus === 'pending' ? pendingHint : item.description,
              }
            }
            const fieldStatus = fieldStatusByUi.get(item.id)
            return fieldStatus ? { ...item, status: fieldStatus } : item
          }),
        )
        setLoadError(null)
      } catch (error) {
        if (cancelled) return
        setLoadError(getErrorMessage(error, '认证状态加载失败'))
      }
    }

    void loadVerificationState()
    return () => {
      cancelled = true
    }
  }, [])

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
                const latest = submissions[0]
                const videoStatus = mapSubmissionStatus(latest?.status)
                const pendingHint =
                  notifications.find((n) => n.type?.includes('resubmission'))?.body ||
                  notifications[0]?.body ||
                  '按提示完成活体视频认证'

                const fieldStatusByUi = new Map<string, FieldItem['status']>()
                for (const submission of fieldSubmissions) {
                  const uiField = mapApiFieldToUi(submission.field_key)
                  if (uiField) fieldStatusByUi.set(uiField, mapSubmissionStatus(submission.status))
                }

                setFieldVerificationTypes(
                  DEFAULT_FIELDS.map((item) => {
                    if (item.id === 'video') {
                      return {
                        ...item,
                        status: videoStatus,
                        description: videoStatus === 'pending' ? pendingHint : item.description,
                      }
                    }
                    const fieldStatus = fieldStatusByUi.get(item.id)
                    return fieldStatus ? { ...item, status: fieldStatus } : item
                  }),
                )
                setLoadError(null)
              } catch (error) {
                setLoadError(getErrorMessage(error, '认证状态加载失败'))
              }
            }

            void reloadState()

            // 显示通知
            if (event.type === 'verification_passed') {
              notifySuccess('验证通过', event.message || '恭喜！您的身份验证已通过')
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
      setStep('video-record')
    } catch (error) {
      notifyError(error, '无法创建认证挑战')
    } finally {
      setIsSubmittingVideo(false)
    }
  }

  const handleRecordVideo = async () => {
    setIsRecording(true)
    setRecordingTime(0)
    const timer = window.setInterval(() => setRecordingTime((prev) => prev + 1), 1000)
    try {
      const video = await recordVideoFromCamera(6000)
      setRecordedVideo(video)
      setStep('video-review')
    } catch (error) {
      notifyError(error, '录制失败')
    } finally {
      window.clearInterval(timer)
      setIsRecording(false)
    }
  }

  const finishVideoSubmission = async () => {
    const token = liveChallenge?.challenge_token
    if (!token) {
      notifyError(new Error('缺少 challenge_token，请返回重试'))
      setStep('video-intro')
      return
    }
    setIsSubmittingVideo(true)
    try {
      await submitLiveVideoVerification({
        challengeToken: token,
        challengePhrase: liveChallenge?.challenge_phrase,
        videoBase64: recordedVideo?.base64,
        contentType: recordedVideo?.mimeType,
      })
      notifySuccess('活体视频已提交，等待审核')
      setStep('video-pending')
    } catch (error) {
      notifyError(error, '视频提交失败')
      setStep('video-review')
    } finally {
      setIsSubmittingVideo(false)
    }
  }

  const handleSubmitField = async () => {
    if (!selectedField) return
    if (!selectedFile) {
      notifyError(new Error('请先选择要上传的文件'))
      return
    }
    setIsSubmittingField(true)
    try {
      await submitFieldVerification({ fieldId: selectedField, file: selectedFile })
      notifySuccess('材料已提交，等待审核')
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
    recordedVideo,
    setRecordedVideo,
    isSubmittingVideo,
    selectedFile,
    setSelectedFile,
    isSubmittingField,
    fileInputRef,
    handleDirectBack: onBack,
    startVideoVerification,
    handleRecordVideo,
    finishVideoSubmission,
    handleSubmitField,
  }
}
