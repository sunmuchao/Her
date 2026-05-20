'use client'

import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  Camera,
  CheckCircle2,
  ChevronRight,
  FileBadge2,
  Loader2,
  Mic,
  RefreshCcw,
  Square,
  Upload,
  Video,
} from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface VerificationFlowPageProps {
  runtimeContext: HerRuntimeContext
  onBack: () => void
}

type TrustHubItem = {
  item_id: string
  item_type?: string
  field_key?: string
  title: string
  status?: string
  status_label?: string
  trigger_reasons?: string[]
  required_materials?: string[]
  failure_reason?: string
  detail_ref?: {
    kind?: string
    submission_id?: string
    source_dsn?: string
    source_table_name?: string
  }
}

type TrustHubResponse = {
  trust_hub: {
    verification_center: {
      items: TrustHubItem[]
    }
  }
}

type ChallengeResponse = {
  challenge: {
    challenge_phrase?: string
    challenge_token?: string
    required_actions?: string[]
  }
}

type LiveSubmission = {
  submission_id: string
  status: string
  challenge_phrase?: string
  review_note?: string
  resubmission_count?: number
  submitted_at?: string
  updated_at?: string
}

type LiveSubmissionListResponse = {
  submissions: LiveSubmission[]
}

type LiveSubmissionResponse = {
  submission: LiveSubmission
}

type FieldPolicy = {
  label: string
  accepted_documents?: string[]
  accepted_evidence_types?: string[]
  accepted_evidence_channels?: string[]
  resubmission_examples?: string[]
}

type FieldPoliciesResponse = {
  policies: {
    fields: Record<string, FieldPolicy>
    income_brackets?: string[]
  }
}

type FieldSubmission = {
  submission_id: string
  field_key: string
  status: string
  declared_value?: string
  evidence_type?: string
  evidence_channel?: string
  source_dsn?: string
  source_table_name?: string
  review_note?: string
  required_documents?: string[]
  updated_at?: string
}

type FieldSubmissionListResponse = {
  submissions: FieldSubmission[]
}

type FieldSubmissionResponse = {
  submission: FieldSubmission
}

type UploadFileState = {
  fileName: string
  contentType: string
  size: number
  base64: string
}

const DEFAULT_SOURCE_DSN =
  process.env.NEXT_PUBLIC_HER_PROFILE_SOURCE_DSN ||
  'mysql://root@127.0.0.1:3307/her?table=profiles'
const DEFAULT_SOURCE_TABLE =
  process.env.NEXT_PUBLIC_HER_PROFILE_SOURCE_TABLE || 'profiles'
const RESUBMITTABLE_STATUSES = new Set(['resubmission_required', 'rejected', 'expired'])
const OPEN_LIVE_STATUSES = new Set([
  'awaiting_submission',
  'submitted',
  'under_review',
  'resubmission_required',
  'rejected',
])

function statusTone(status?: string) {
  switch (status) {
    case 'approved':
      return 'text-emerald-600 bg-emerald-50 border-emerald-200'
    case 'submitted':
    case 'under_review':
      return 'text-amber-700 bg-amber-50 border-amber-200'
    case 'resubmission_required':
    case 'rejected':
    case 'expired':
      return 'text-rose-700 bg-rose-50 border-rose-200'
    default:
      return 'text-muted-foreground bg-secondary border-border/40'
  }
}

function humanStatus(status?: string) {
  switch (status) {
    case 'approved':
      return '已通过'
    case 'submitted':
      return '已提交'
    case 'under_review':
      return '审核中'
    case 'resubmission_required':
      return '待补交'
    case 'rejected':
      return '未通过'
    case 'expired':
      return '已过期'
    case 'awaiting_submission':
      return '待提交'
    default:
      return status || '未开始'
  }
}

function formatTime(value?: string) {
  if (!value) {
    return '刚刚'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function blobToBase64(blob: Blob) {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.onload = () => {
      const result = String(reader.result || '')
      const base64 = result.includes(',') ? result.split(',')[1] : result
      resolve(base64)
    }
    reader.readAsDataURL(blob)
  })
}

function preferredRecordingMimeType() {
  if (typeof window === 'undefined' || typeof MediaRecorder === 'undefined') {
    return 'video/webm'
  }
  const candidates = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) || 'video/webm'
}

export default function VerificationFlowPage({
  runtimeContext,
  onBack,
}: VerificationFlowPageProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const previewUrlRef = useRef<string | null>(null)

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const [items, setItems] = useState<TrustHubItem[]>([])
  const [challenge, setChallenge] = useState<ChallengeResponse['challenge'] | null>(null)
  const [challengeLoading, setChallengeLoading] = useState(false)
  const [liveSubmissions, setLiveSubmissions] = useState<LiveSubmission[]>([])
  const [policies, setPolicies] = useState<Record<string, FieldPolicy>>({})
  const [incomeBrackets, setIncomeBrackets] = useState<string[]>([])
  const [fieldSubmissions, setFieldSubmissions] = useState<FieldSubmission[]>([])

  const [cameraReady, setCameraReady] = useState(false)
  const [recording, setRecording] = useState(false)
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null)
  const [recordedPreviewUrl, setRecordedPreviewUrl] = useState<string | null>(null)
  const [liveSubmitting, setLiveSubmitting] = useState(false)

  const [selectedFieldKey, setSelectedFieldKey] = useState('education')
  const [declaredValue, setDeclaredValue] = useState('')
  const [evidenceType, setEvidenceType] = useState('')
  const [evidenceChannel, setEvidenceChannel] = useState('document_upload')
  const [fieldNote, setFieldNote] = useState('')
  const [fieldFile, setFieldFile] = useState<UploadFileState | null>(null)
  const [fieldSubmitting, setFieldSubmitting] = useState(false)

  const sourceDsn = DEFAULT_SOURCE_DSN
  const sourceTableName = DEFAULT_SOURCE_TABLE

  async function loadAllData(silent = false) {
    if (!runtimeContext.userId) {
      setLoading(false)
      setError('缺少 user_id，当前无法读取认证事项。')
      return
    }
    if (!silent) {
      setLoading(true)
    } else {
      setRefreshing(true)
    }
    try {
      const [trustHubPayload, livePayload, policyPayload, fieldPayload] = await Promise.all([
        gatewayJson<TrustHubResponse>(
          `/v1/user-center/trust-hub${queryString({
            user_id: runtimeContext.userId,
            profile_id: runtimeContext.profileId,
          })}`,
        ),
        gatewayJson<LiveSubmissionListResponse>(
          `/v1/verifications/live-video-submissions${queryString({
            user_id: runtimeContext.userId,
            profile_id: runtimeContext.profileId,
            limit: 20,
          })}`,
        ),
        gatewayJson<FieldPoliciesResponse>('/v1/profile-verifications/policies'),
        gatewayJson<FieldSubmissionListResponse>(
          `/v1/profile-verifications/submissions${queryString({
            subject_user_id: runtimeContext.userId,
            profile_id: runtimeContext.profileId,
            limit: 20,
          })}`,
        ),
      ])

      setItems(trustHubPayload.trust_hub.verification_center.items || [])
      setLiveSubmissions(livePayload.submissions || [])
      setPolicies(policyPayload.policies.fields || {})
      setIncomeBrackets(policyPayload.policies.income_brackets || [])
      setFieldSubmissions(fieldPayload.submissions || [])
      setError(null)
      setSelectedFieldKey((current) => {
        if (current && policyPayload.policies.fields[current]) {
          return current
        }
        return Object.keys(policyPayload.policies.fields)[0] || 'education'
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '认证数据读取失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    void loadAllData()
  }, [runtimeContext.profileId, runtimeContext.userId])

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current)
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
      }
    }
  }, [])

  useEffect(() => {
    const policy = policies[selectedFieldKey]
    if (!policy) {
      return
    }
    setEvidenceType((current) => current || policy.accepted_evidence_types?.[0] || '')
    setEvidenceChannel((current) => current || policy.accepted_evidence_channels?.[0] || 'document_upload')
  }, [policies, selectedFieldKey])

  const liveTrustItem = items.find(
    (item) =>
      item.item_type === 'photo_review_request' ||
      item.detail_ref?.kind === 'verification_submission',
  )
  const latestLiveSubmission = liveSubmissions.find((item) => OPEN_LIVE_STATUSES.has(item.status)) || liveSubmissions[0]
  const currentLiveSubmissionId =
    liveTrustItem?.detail_ref?.submission_id || latestLiveSubmission?.submission_id
  const currentLiveStatus = latestLiveSubmission?.status || liveTrustItem?.status
  const liveNeedsResubmit =
    !!currentLiveSubmissionId && RESUBMITTABLE_STATUSES.has(currentLiveStatus || '')

  const selectedPolicy = policies[selectedFieldKey]
  const fieldTrustItem = items.find((item) => item.field_key === selectedFieldKey)
  const existingFieldSubmission =
    fieldSubmissions.find((item) => item.field_key === selectedFieldKey && RESUBMITTABLE_STATUSES.has(item.status)) ||
    fieldSubmissions.find((item) => item.field_key === selectedFieldKey)
  const existingFieldSubmissionId =
    fieldTrustItem?.detail_ref?.submission_id || existingFieldSubmission?.submission_id
  const fieldNeedsResubmit =
    !!existingFieldSubmissionId && RESUBMITTABLE_STATUSES.has(existingFieldSubmission?.status || fieldTrustItem?.status || '')
  const effectiveSourceDsn =
    existingFieldSubmission?.source_dsn || fieldTrustItem?.detail_ref?.source_dsn || sourceDsn
  const effectiveSourceTable =
    existingFieldSubmission?.source_table_name || fieldTrustItem?.detail_ref?.source_table_name || sourceTableName

  async function createChallenge() {
    if (!runtimeContext.userId || !runtimeContext.profileId) {
      setError('活体 challenge 需要 user_id 和 profile_id。')
      return
    }
    setChallengeLoading(true)
    setError(null)
    setSuccessMessage(null)
    try {
      const payload = await gatewayJson<ChallengeResponse>('/v1/verifications/live-video-challenges', {
        method: 'POST',
        body: JSON.stringify({
          user_id: runtimeContext.userId,
          profile_id: runtimeContext.profileId,
        }),
      })
      setChallenge(payload.challenge)
    } catch (err) {
      setError(err instanceof Error ? err.message : '活体 challenge 创建失败')
    } finally {
      setChallengeLoading(false)
    }
  }

  async function enableCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('当前浏览器不支持摄像头录制。')
      return
    }
    setError(null)
    setSuccessMessage(null)
    try {
      if (!challenge) {
        await createChallenge()
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 720 }, height: { ideal: 1280 } },
        audio: true,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => undefined)
      }
      setCameraReady(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '摄像头启动失败')
    }
  }

  function stopCamera() {
    recorderRef.current?.stop()
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setCameraReady(false)
    setRecording(false)
  }

  function startRecording() {
    if (!streamRef.current) {
      setError('请先开启摄像头。')
      return
    }
    try {
      chunksRef.current = []
      const mimeType = preferredRecordingMimeType()
      const recorder = new MediaRecorder(streamRef.current, { mimeType })
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'video/webm' })
        if (previewUrlRef.current) {
          URL.revokeObjectURL(previewUrlRef.current)
        }
        const nextPreview = URL.createObjectURL(blob)
        previewUrlRef.current = nextPreview
        setRecordedBlob(blob)
        setRecordedPreviewUrl(nextPreview)
        setRecording(false)
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop())
          streamRef.current = null
        }
        if (videoRef.current) {
          videoRef.current.srcObject = null
        }
        setCameraReady(false)
      }
      recorder.start()
      setRecordedBlob(null)
      setRecordedPreviewUrl(null)
      setRecording(true)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '开始录制失败')
    }
  }

  function stopRecording() {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
  }

  async function submitLiveVideo() {
    if (!runtimeContext.userId) {
      setError('缺少 user_id，无法提交活体验证。')
      return
    }
    if (!recordedBlob) {
      setError('请先录制活体视频。')
      return
    }
    setLiveSubmitting(true)
    setError(null)
    setSuccessMessage(null)
    try {
      const fileName = `live-verification-${Date.now()}.webm`
      const videoBase64 = await blobToBase64(recordedBlob)
      const path = liveNeedsResubmit && currentLiveSubmissionId
        ? `/v1/verifications/live-video-submissions/${currentLiveSubmissionId}/resubmit`
        : '/v1/verifications/live-video-submissions'
      const payload = await gatewayJson<LiveSubmissionResponse>(path, {
        method: 'POST',
        body: JSON.stringify({
          user_id: runtimeContext.userId,
          profile_id: runtimeContext.profileId,
          submission_id: liveNeedsResubmit ? undefined : currentLiveSubmissionId,
          video_base64: videoBase64,
          file_name: fileName,
          content_type: recordedBlob.type || 'video/webm',
          challenge_phrase: challenge?.challenge_phrase,
          metadata: {
            capture_mode: 'browser_media_recorder',
            challenge_phrase_rendered: !!challenge?.challenge_phrase,
            action_hint: challenge?.required_actions || [],
          },
        }),
      })
      setSuccessMessage(
        `活体视频已提交，当前状态：${humanStatus(payload.submission.status)}。`,
      )
      setRecordedBlob(null)
      setRecordedPreviewUrl(null)
      await loadAllData(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '活体视频提交失败')
    } finally {
      setLiveSubmitting(false)
    }
  }

  async function handleFieldFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      setFieldFile(null)
      return
    }
    try {
      const base64 = await blobToBase64(file)
      setFieldFile({
        fileName: file.name,
        contentType: file.type || 'application/octet-stream',
        size: file.size,
        base64,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '材料读取失败')
    }
  }

  async function submitFieldVerification() {
    if (!runtimeContext.profileId || !runtimeContext.userId) {
      setError('字段认证需要 profile_id 和 user_id。')
      return
    }
    if (!selectedFieldKey || !selectedPolicy) {
      setError('字段策略加载失败，暂时无法提交。')
      return
    }
    if (!declaredValue.trim()) {
      setError('请先填写你的声明字段内容。')
      return
    }
    if (!fieldFile) {
      setError('请先选择认证材料。')
      return
    }
    if (!effectiveSourceDsn) {
      setError('缺少 source_dsn，无法提交字段认证。')
      return
    }
    setFieldSubmitting(true)
    setError(null)
    setSuccessMessage(null)
    try {
      const evidence = {
        field_key: selectedFieldKey,
        note: fieldNote.trim() || undefined,
        files: [
          {
            file_name: fieldFile.fileName,
            content_type: fieldFile.contentType,
            size_bytes: fieldFile.size,
            base64: fieldFile.base64,
          },
        ],
      }
      const path = fieldNeedsResubmit && existingFieldSubmissionId
        ? `/v1/profile-verifications/submissions/${existingFieldSubmissionId}/resubmit`
        : '/v1/profile-verifications/submissions'
      const payload = await gatewayJson<FieldSubmissionResponse>(path, {
        method: 'POST',
        body: JSON.stringify({
          field_key: selectedFieldKey,
          profile_id: runtimeContext.profileId,
          subject_user_id: runtimeContext.userId,
          source_dsn: effectiveSourceDsn,
          source_table_name: effectiveSourceTable,
          declared_value: declaredValue.trim(),
          evidence,
          evidence_type,
          evidence_channel,
          required_documents: selectedPolicy.accepted_documents || [],
        }),
      })
      setSuccessMessage(
        `${selectedPolicy.label}材料已提交，当前状态：${humanStatus(payload.submission.status)}。`,
      )
      setFieldFile(null)
      setFieldNote('')
      await loadAllData(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '字段认证提交失败')
    } finally {
      setFieldSubmitting(false)
    }
  }

  const trustFieldItems = items.filter(
    (item) =>
      item.item_type === 'field_verification_submission' ||
      item.item_type === 'field_verification_request',
  )

  return (
    <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={onBack}
              className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="font-medium text-foreground">认证与补件</h1>
              <p className="text-xs text-muted-foreground mt-0.5">视频活体 + 字段材料均已接真实后端流程</p>
            </div>
            <button
              onClick={() => void loadAllData(true)}
              disabled={refreshing}
              className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors"
            >
              {refreshing ? (
                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              ) : (
                <RefreshCcw className="w-4 h-4 text-muted-foreground" />
              )}
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-6 space-y-5">
        <section className="rounded-3xl bg-gradient-to-br from-card to-blush/25 p-5 border border-border/40 shadow-soft">
          <h2 className="editorial-title text-2xl text-foreground">认证中心</h2>
          <p className="mt-2 text-sm leading-6 text-taupe">
            这里直接连后端 challenge、活体提交、字段认证提交与重提状态。用户现在可以在手机壳式界面里完成真实操作。
          </p>
        </section>

        {loading ? (
          <div className="flex items-center justify-center rounded-2xl bg-card p-10 text-muted-foreground shadow-soft border border-border/30">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            正在同步认证数据
          </div>
        ) : null}

        {error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {successMessage ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700 flex items-start gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
            {successMessage}
          </div>
        ) : null}

        <section className="space-y-3 rounded-3xl border border-border/30 bg-card p-4 shadow-soft">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-rose-soft/60">
              <Video className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-medium text-foreground">活体视频录制上传</p>
                <span className={`rounded-full border px-2.5 py-1 text-[11px] ${statusTone(currentLiveStatus)}`}>
                  {humanStatus(currentLiveStatus)}
                </span>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {liveNeedsResubmit
                  ? '当前是补录流程，提交后会直接覆盖到原审核单。'
                  : '录制 5-10 秒真人视频并提交到后端审核。'}
              </p>
              {latestLiveSubmission?.updated_at ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  最近更新：{formatTime(latestLiveSubmission.updated_at)}
                </p>
              ) : null}
            </div>
          </div>

          <button
            onClick={() => void createChallenge()}
            disabled={challengeLoading}
            className="w-full rounded-2xl border border-rose-soft/40 bg-gradient-to-r from-blush/40 to-card p-4 text-left"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-background/90">
                {challengeLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <Camera className="h-4 w-4 text-primary" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">刷新活体口令</p>
                <p className="text-xs text-muted-foreground mt-1">先拿最新 challenge phrase，再开始录制。</p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </button>

          {challenge ? (
            <div className="rounded-2xl border border-border/40 bg-background p-4">
              <p className="text-xs text-muted-foreground">请在录制时自然读出下面口令并完成动作</p>
              <p className="mt-2 text-base font-medium text-foreground">{challenge.challenge_phrase || '未返回 challenge_phrase'}</p>
              {challenge.required_actions?.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {challenge.required_actions.map((action) => (
                    <span key={action} className="rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
                      {action}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="rounded-2xl overflow-hidden border border-border/30 bg-secondary/40">
            <video
              ref={videoRef}
              muted
              playsInline
              autoPlay
              className={`h-72 w-full object-cover ${cameraReady ? 'block' : 'hidden'}`}
            />
            {!cameraReady && recordedPreviewUrl ? (
              <video src={recordedPreviewUrl} controls playsInline className="h-72 w-full object-cover" />
            ) : null}
            {!cameraReady && !recordedPreviewUrl ? (
              <div className="h-72 w-full flex flex-col items-center justify-center text-center px-6">
                <Camera className="h-8 w-8 text-muted-foreground" />
                <p className="mt-3 text-sm font-medium text-foreground">开启前置摄像头后即可录制</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  保持正脸、自然光、无遮挡，同时读出口令并完成动作。
                </p>
              </div>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => void enableCamera()}
              disabled={cameraReady || recording}
              className="rounded-2xl bg-secondary px-4 py-3 text-sm font-medium text-foreground disabled:opacity-50"
            >
              开启摄像头
            </button>
            <button
              onClick={cameraReady ? stopCamera : undefined}
              disabled={!cameraReady || recording}
              className="rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm font-medium text-foreground disabled:opacity-50"
            >
              关闭摄像头
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={recording ? stopRecording : startRecording}
              disabled={!cameraReady}
              className="rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              {recording ? '结束录制' : '开始录制'}
            </button>
            <button
              onClick={() => void submitLiveVideo()}
              disabled={!recordedBlob || liveSubmitting}
              className="rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm font-medium text-foreground disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {liveSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              提交视频
            </button>
          </div>

          {latestLiveSubmission?.review_note ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
              审核备注：{latestLiveSubmission.review_note}
            </div>
          ) : null}
        </section>

        <section className="space-y-4 rounded-3xl border border-border/30 bg-card p-4 shadow-soft">
          <div className="flex items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-secondary">
              <FileBadge2 className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">字段认证上传</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                直接提交学历、职业、收入材料到字段认证接口；若已有退回单，会自动走补件重提。
              </p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {Object.entries(policies).map(([key, policy]) => (
              <button
                key={key}
                onClick={() => setSelectedFieldKey(key)}
                className={`rounded-2xl px-3 py-3 text-sm transition-colors ${
                  selectedFieldKey === key
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-foreground'
                }`}
              >
                {policy.label}
              </button>
            ))}
          </div>

          {selectedPolicy ? (
            <>
              <div className="rounded-2xl border border-border/30 bg-background p-4 space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`rounded-full border px-2.5 py-1 text-[11px] ${statusTone(existingFieldSubmission?.status || fieldTrustItem?.status)}`}>
                    {humanStatus(existingFieldSubmission?.status || fieldTrustItem?.status || 'awaiting_submission')}
                  </span>
                  {fieldNeedsResubmit ? (
                    <span className="rounded-full bg-rose-50 px-2.5 py-1 text-[11px] text-rose-700">
                      当前将走补件重提
                    </span>
                  ) : null}
                </div>
                {existingFieldSubmission?.review_note || fieldTrustItem?.failure_reason ? (
                  <p className="text-xs text-rose-700">
                    审核备注：{existingFieldSubmission?.review_note || fieldTrustItem?.failure_reason}
                  </p>
                ) : null}
                <div>
                  <p className="text-xs text-muted-foreground">可接受材料</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(selectedPolicy.accepted_documents || []).map((item) => (
                      <span key={item} className="rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <label className="block">
                <span className="text-xs text-muted-foreground">声明内容</span>
                {selectedFieldKey === 'income' ? (
                  <select
                    value={declaredValue}
                    onChange={(event) => setDeclaredValue(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm text-foreground outline-none"
                  >
                    <option value="">请选择收入区间</option>
                    {incomeBrackets.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={declaredValue}
                    onChange={(event) => setDeclaredValue(event.target.value)}
                    placeholder={`填写你的${selectedPolicy.label}声明`}
                    className="mt-2 w-full rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm text-foreground outline-none"
                  />
                )}
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="block">
                  <span className="text-xs text-muted-foreground">材料类型</span>
                  <select
                    value={evidenceType}
                    onChange={(event) => setEvidenceType(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm text-foreground outline-none"
                  >
                    {(selectedPolicy.accepted_evidence_types || []).map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block">
                  <span className="text-xs text-muted-foreground">提交渠道</span>
                  <select
                    value={evidenceChannel}
                    onChange={(event) => setEvidenceChannel(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm text-foreground outline-none"
                  >
                    {(selectedPolicy.accepted_evidence_channels || []).map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="block">
                <span className="text-xs text-muted-foreground">上传材料</span>
                <input
                  type="file"
                  accept="image/*,.pdf"
                  onChange={(event) => void handleFieldFileChange(event)}
                  className="mt-2 block w-full rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm text-foreground"
                />
              </label>

              {fieldFile ? (
                <div className="rounded-2xl border border-border/30 bg-background p-3 text-xs text-muted-foreground">
                  已选择：{fieldFile.fileName} · {(fieldFile.size / 1024).toFixed(1)} KB
                </div>
              ) : null}

              <label className="block">
                <span className="text-xs text-muted-foreground">补充说明</span>
                <textarea
                  value={fieldNote}
                  onChange={(event) => setFieldNote(event.target.value)}
                  rows={3}
                  placeholder="补充说明材料对应关系、时间范围、姓名一致性等。"
                  className="mt-2 w-full rounded-2xl border border-border/40 bg-background px-4 py-3 text-sm text-foreground outline-none resize-none"
                />
              </label>

              <button
                onClick={() => void submitFieldVerification()}
                disabled={fieldSubmitting}
                className="w-full rounded-2xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {fieldSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {fieldNeedsResubmit ? '提交补件' : '提交字段认证'}
              </button>

              <div className="rounded-2xl bg-secondary/60 p-4 text-xs text-muted-foreground">
                当前提交源：{effectiveSourceTable || 'profiles'} · {effectiveSourceDsn}
              </div>
            </>
          ) : (
            <div className="rounded-2xl border border-border/30 bg-background p-4 text-sm text-muted-foreground">
              当前没有可用字段认证策略。
            </div>
          )}
        </section>

        <section>
          <h2 className="text-sm font-medium text-foreground mb-3">待处理认证事项</h2>
          <div className="space-y-3">
            {items.length === 0 ? (
              <div className="rounded-2xl border border-border/30 bg-card p-4 text-sm text-muted-foreground shadow-soft">
                当前没有待处理认证事项。
              </div>
            ) : (
              items.map((item) => (
                <div
                  key={item.item_id}
                  className="rounded-2xl border border-border/30 bg-card p-4 text-left shadow-soft"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
                      <Upload className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-medium text-foreground">{item.title}</p>
                        <span className={`rounded border px-2 py-0.5 text-[10px] ${statusTone(item.status)}`}>
                          {item.status_label || humanStatus(item.status)}
                        </span>
                      </div>
                      {item.trigger_reasons?.length ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          {item.trigger_reasons.join('；')}
                        </p>
                      ) : null}
                      {item.required_materials?.length ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          所需材料：{item.required_materials.join('、')}
                        </p>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        {trustFieldItems.length > 0 ? (
          <section className="rounded-2xl bg-secondary/60 p-4 text-xs text-muted-foreground space-y-2">
            {trustFieldItems.map((item) => (
              <div key={item.item_id}>
                {item.title}：{item.status_label || humanStatus(item.status)}
              </div>
            ))}
          </section>
        ) : null}

        <div className="rounded-2xl bg-secondary/60 p-4 text-xs text-muted-foreground flex items-start gap-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          浏览器会把录制视频和上传材料转成 base64 走现有网关 JSON 接口；这符合当前后端能力边界，没有额外引入 OSS 或 multipart 假设。
        </div>
      </div>
    </div>
  )
}
