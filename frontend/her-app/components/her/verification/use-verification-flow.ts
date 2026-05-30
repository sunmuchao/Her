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
import { getUserId } from '@/lib/auth/session'
import { getErrorMessage } from '@/lib/api/errors'

export type VerificationStep = 'select' | 'video-intro' | 'video-record' | 'video-review' | 'video-pending' | 'field-upload' | 'field-pending'

export type FieldItem = {
  id: string
  name: string
  description: string
  status: 'verified' | 'pending' | 'unverified'
}

const DEFAULT_FIELDS: FieldItem[] = [
  {
    id: 'education',
    name: '学历认证',
    description: '提供学位证书或学信网截图',
    status: 'unverified',
  },
  {
    id: 'occupation',
    name: '职业认证',
    description: '提供在职证明或工牌照片',
    status: 'unverified',
  },
  {
    id: 'income',
    name: '收入认证',
    description: '提供近三个月银行流水',
    status: 'unverified',
  },
  {
    id: 'video',
    name: '活体视频认证',
    description: '录制真人视频确保真实性',
    status: 'unverified',
  },
]

function mapSubmissionStatus(status?: string): FieldItem['status'] {
  const text = (status || '').toLowerCase()
  if (['approved', 'verified', 'completed'].includes(text)) return 'verified'
  if (['submitted', 'under_review', 'awaiting_submission', 'resubmission_required'].includes(text)) {
    return 'pending'
  }
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
  if (target === 'video') return 'video-intro'
  if (target === 'education' || target === 'occupation' || target === 'income') return 'field-upload'
  return 'select'
}

export function useVerificationFlow() {
  const searchParams = useSearchParams()
  const initialTarget = searchParams.get('target')
  const directEntry = Boolean(initialTarget)
  const [fieldVerificationTypes, setFieldVerificationTypes] = useState<FieldItem[]>(DEFAULT_FIELDS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [step, setStep] = useState<VerificationStep>(() => resolveInitialStep(initialTarget))
  const [selectedField, setSelectedField] = useState<string | null>(() =>
    initialTarget === 'education' || initialTarget === 'occupation' || initialTarget === 'income'
      ? initialTarget
      : null,
  )
  const [isRecording, setIsRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [liveChallenge, setLiveChallenge] = useState<LiveVideoChallenge | null>(null)
  const [recordedVideo, setRecordedVideo] = useState<RecordedVideo | null>(null)
  const [isSubmittingVideo, setIsSubmittingVideo] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isSubmittingField, setIsSubmittingField] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 加载认证状态
  useEffect(() => {
    const userId = getUserId()
    if (!userId) {
      setIsLoading(false)
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
          if (uiField) {
            fieldStatusByUi.set(uiField, mapSubmissionStatus(submission.status))
          }
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
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadVerificationState()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (isLoading || loadError) return
    if (!initialTarget) return

    if (initialTarget === 'video') {
      if (step === 'select') {
        setStep('video-intro')
      }
      return
    }

    const targetField = fieldVerificationTypes.find((field) => field.id === initialTarget)
    if (targetField && targetField.status !== 'verified' && step === 'select') {
      setSelectedField(targetField.id)
      setStep('field-upload')
    }
  }, [initialTarget, isLoading, loadError, fieldVerificationTypes, step])

  // 计算进度
  const verifiedCount = fieldVerificationTypes.filter(f => f.status === 'verified').length
  const progress = (verifiedCount / fieldVerificationTypes.length) * 100

  // 视频认证相关方法
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
    const timer = window.setInterval(() => {
      setRecordingTime((prev) => prev + 1)
    }, 1000)
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

  // 文件认证相关方法
  const handleStartFieldVerification = (fieldId: string) => {
    setSelectedField(fieldId)
    setStep('field-upload')
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

  // 状态样式辅助函数
  const getStatusStyles = (status: string) => {
    switch (status) {
      case 'verified':
        return { bg: 'bg-primary/10', text: 'text-primary', icon: 'text-primary' }
      case 'pending':
        return { bg: 'bg-gold/10', text: 'text-gold', icon: 'text-gold' }
      default:
        return { bg: 'bg-secondary', text: 'text-muted-foreground', icon: 'text-muted-foreground' }
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'verified': return '已认证'
      case 'pending': return '审核中'
      default: return '未认证'
    }
  }

  return {
    // 状态
    fieldVerificationTypes,
    loadError,
    isLoading,
    step,
    setStep,
    selectedField,
    setSelectedField,
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
    verifiedCount,
    progress,
    directEntry,
    // 方法
    startVideoVerification,
    handleRecordVideo,
    finishVideoSubmission,
    handleStartFieldVerification,
    handleSubmitField,
    getStatusStyles,
    getStatusText,
  }
}
