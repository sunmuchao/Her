'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, Camera, RotateCcw, CheckCircle, Clock, AlertCircle, Upload, ChevronRight, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  createLiveVideoChallenge,
  listVerificationNotifications,
  listVerificationSubmissions,
  submitLiveVideoVerification,
  type LiveVideoChallenge,
} from '@/lib/api/endpoints/verification'
import { notifyError, notifySuccess } from '@/lib/notify'
import { getUserId } from '@/lib/auth/session'
import { getErrorMessage } from '@/lib/api/errors'
import { FadeIn, PageTransition } from './ui/animations'
import { ProgressRing } from './ui/progress-ring'
import { ErrorState } from './ui/error-state'

interface VerificationFlowPageProps {
  onBack: () => void
}

type VerificationStep = 'select' | 'video-intro' | 'video-record' | 'video-review' | 'video-pending' | 'field-upload' | 'field-pending'

type FieldItem = {
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

export default function VerificationFlowPage({ onBack }: VerificationFlowPageProps) {
  const [fieldVerificationTypes, setFieldVerificationTypes] = useState<FieldItem[]>(DEFAULT_FIELDS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [step, setStep] = useState<VerificationStep>('select')
  const [selectedField, setSelectedField] = useState<string | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [liveChallenge, setLiveChallenge] = useState<LiveVideoChallenge | null>(null)
  const [isSubmittingVideo, setIsSubmittingVideo] = useState(false)

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
        const [submissions, notifications] = await Promise.all([
          listVerificationSubmissions(),
          listVerificationNotifications(),
        ])
        if (cancelled) return
        const latest = submissions[0]
        const videoStatus = mapSubmissionStatus(latest?.status)
        const pendingHint =
          notifications.find((n) => n.type?.includes('resubmission'))?.body ||
          notifications[0]?.body ||
          '按提示完成活体视频认证'

        setFieldVerificationTypes(
          DEFAULT_FIELDS.map((item) =>
            item.id === 'video'
              ? {
                  ...item,
                  status: videoStatus,
                  description: videoStatus === 'pending' ? pendingHint : item.description,
                }
              : item,
          ),
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

  const handleStartVideoVerification = () => {
    setStep('video-intro')
  }

  const handleStartFieldVerification = (fieldId: string) => {
    setSelectedField(fieldId)
    setStep('field-upload')
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

  const simulateRecording = () => {
    setIsRecording(true)
    setRecordingTime(0)
    const interval = setInterval(() => {
      setRecordingTime((prev) => {
        if (prev >= 5) {
          clearInterval(interval)
          setIsRecording(false)
          void finishVideoSubmission()
          return 5
        }
        return prev + 1
      })
    }, 1000)
  }

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

  // Selection page
  if (step === 'select') {
    const verifiedCount = fieldVerificationTypes.filter(f => f.status === 'verified').length
    const progress = (verifiedCount / fieldVerificationTypes.length) * 100
    
    return (
      <PageTransition className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={onBack}
              className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors focus-ring"
              aria-label="返回"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            <h1 className="font-medium text-foreground">去认证</h1>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-6 space-y-4">
          {loadError && (
            <ErrorState message={loadError} onRetry={() => window.location.reload()} />
          )}
          {isLoading && !loadError && (
            <p className="text-sm text-muted-foreground px-1">正在同步认证状态…</p>
          )}
          {/* Progress overview */}
          <FadeIn>
            <div className="flex items-center gap-4 p-4 bg-card border border-border rounded-xl">
              <ProgressRing progress={progress} size={56} strokeWidth={4} color="rose" showPercentage />
              <div>
                <h2 className="font-medium">认证进度</h2>
                <p className="text-sm text-muted-foreground">{verifiedCount}/{fieldVerificationTypes.length} 项已完成</p>
              </div>
            </div>
          </FadeIn>
          
          <p className="text-sm text-muted-foreground">
            完成认证可提升你的可信度，让更多优质用户愿意了解你
          </p>

          {fieldVerificationTypes.map((field, index) => {
            const styles = getStatusStyles(field.status)
            return (
              <FadeIn key={field.id} delay={index * 50}>
                <button
                  onClick={() => {
                    if (field.id === 'video' && field.status !== 'verified') {
                      handleStartVideoVerification()
                    } else if (field.status === 'unverified') {
                      handleStartFieldVerification(field.id)
                    }
                  }}
                  disabled={field.status === 'verified'}
                  className={cn(
                    'w-full bg-card rounded-xl p-4 border border-border transition-all text-left focus-ring',
                    field.status !== 'verified' && 'hover:bg-secondary/30 hover:border-primary/20'
                  )}
                  aria-label={`${field.name}：${getStatusText(field.status)}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={cn('w-10 h-10 rounded-full flex items-center justify-center', styles.bg)}>
                      {field.status === 'verified' ? (
                        <CheckCircle className={cn('w-5 h-5', styles.icon)} />
                      ) : field.status === 'pending' ? (
                        <Clock className={cn('w-5 h-5', styles.icon)} />
                      ) : (
                        <Upload className={cn('w-5 h-5', styles.icon)} />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-medium text-foreground">{field.name}</h3>
                        <span className={cn('text-[10px] px-1.5 py-0.5 rounded', styles.bg, styles.text)}>
                          {getStatusText(field.status)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{field.description}</p>
                    </div>
                    {field.status === 'unverified' && (
                      <ChevronRight className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
                    )}
                  </div>
                </button>
              </FadeIn>
            )
          })}
        </div>
      </PageTransition>
    )
  }

  // Video verification intro
  if (step === 'video-intro') {
    return (
      <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setStep('select')}
              className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            <h1 className="font-medium text-foreground">活体视频认证</h1>
          </div>
        </header>

        <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
          <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center mb-6">
            <Camera className="w-10 h-10 text-primary" />
          </div>
          
          <h2 className="font-serif text-xl text-foreground mb-3">验证真实的你</h2>
          <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
            为了保护真实用户的体验，我们需要你完成一个简短的视频认证。
          </p>

          <div className="w-full bg-secondary/50 rounded-xl p-4 text-left mb-8">
            <h4 className="text-sm font-medium text-foreground mb-2">你需要做什么</h4>
            <ul className="text-sm text-muted-foreground space-y-1">
              <li>• 确保光线充足，面部清晰可见</li>
              <li>• 按照提示完成指定动作</li>
              <li>• 保持自然表情即可</li>
            </ul>
          </div>

          <button
            type="button"
            disabled={isSubmittingVideo}
            onClick={() => {
              void (async () => {
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
              })()
            }}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium disabled:opacity-60"
          >
            {isSubmittingVideo ? '准备中…' : '开始认证'}
          </button>
          {liveChallenge?.challenge_phrase && (
            <p className="mt-4 text-sm text-muted-foreground">{liveChallenge.challenge_phrase}</p>
          )}
        </div>
      </div>
    )
  }

  // Video recording
  if (step === 'video-record') {
    return (
      <div className="min-h-screen bg-foreground max-w-md mx-auto flex flex-col relative">
        <div className="absolute inset-0 bg-gradient-to-b from-foreground/80 to-foreground" />
        
        <button
          onClick={() => setStep('video-intro')}
          className="absolute top-12 right-5 w-10 h-10 rounded-full bg-background/20 flex items-center justify-center z-10"
        >
          <X className="w-5 h-5 text-white" />
        </button>

        <div className="relative z-10 flex-1 flex flex-col items-center justify-between py-16 px-8">
          <div className="flex-1 flex items-center justify-center">
            <div className="w-64 h-80 rounded-[40%] border-4 border-dashed border-white/40 flex items-center justify-center">
              <p className="text-white/60 text-sm">将面部置于框内</p>
            </div>
          </div>

          <div className="text-center mb-8">
            <h3 className="text-white text-xl font-medium mb-2">
              {isRecording ? '请缓慢转动头部' : '准备好后点击开始'}
            </h3>
            <p className="text-white/60 text-sm">
              {isRecording ? `录制中 ${recordingTime}s / 5s` : '确保面部光线充足'}
            </p>
          </div>

          <button
            onClick={simulateRecording}
            disabled={isRecording}
            className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
              isRecording ? 'bg-rose animate-pulse' : 'bg-white hover:scale-105'
            }`}
          >
            {isRecording ? (
              <div className="w-8 h-8 rounded-md bg-white" />
            ) : (
              <div className="w-16 h-16 rounded-full bg-primary" />
            )}
          </button>
        </div>
      </div>
    )
  }

  // Video review
  if (step === 'video-review') {
    return (
      <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setStep('video-record')}
              className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            <h1 className="font-medium text-foreground">确认提交</h1>
          </div>
        </header>

        <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
          <div className="w-48 h-64 rounded-2xl bg-secondary mb-6 overflow-hidden">
            <div className="w-full h-full bg-primary/5 flex items-center justify-center">
              <Camera className="w-12 h-12 text-muted-foreground" />
            </div>
          </div>

          <h2 className="text-lg font-medium text-foreground mb-2">视频录制完成</h2>
          <p className="text-sm text-muted-foreground mb-8">
            请确认视频清晰后提交审核
          </p>

          <div className="w-full space-y-3">
            <button
              onClick={() => setStep('video-pending')}
              className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium"
            >
              确认提交
            </button>
            <button
              onClick={() => setStep('video-record')}
              className="w-full py-4 bg-secondary rounded-2xl text-foreground font-medium flex items-center justify-center gap-2"
            >
              <RotateCcw className="w-4 h-4" />
              重新录制
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Video pending
  if (step === 'video-pending') {
    return (
      <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3">
            <h1 className="font-medium text-foreground">提交成功</h1>
          </div>
        </header>

        <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
          <div className="w-16 h-16 rounded-full bg-gold/10 flex items-center justify-center mb-6">
            <Clock className="w-8 h-8 text-gold" />
          </div>

          <h2 className="font-serif text-xl text-foreground mb-3">审核中</h2>
          <p className="text-sm text-muted-foreground mb-2">
            你的视频认证材料已提交
          </p>
          <p className="text-sm text-muted-foreground mb-8">
            预计1-2个工作日内完成审核
          </p>

          <button
            onClick={onBack}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium"
          >
            返回
          </button>
        </div>
      </div>
    )
  }

  // Field upload
  if (step === 'field-upload') {
    const field = fieldVerificationTypes.find(f => f.id === selectedField)
    
    return (
      <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setStep('select')}
              className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            <h1 className="font-medium text-foreground">{field?.name}</h1>
          </div>
        </header>

        <div className="flex-1 px-5 py-6">
          <p className="text-sm text-muted-foreground mb-6">
            {field?.description}，我们会在1-2个工作日内完成审核。
          </p>

          <div className="border-2 border-dashed border-border rounded-xl p-8 text-center mb-6">
            <div className="w-14 h-14 rounded-full bg-secondary mx-auto flex items-center justify-center mb-4">
              <Upload className="w-7 h-7 text-muted-foreground" />
            </div>
            <p className="text-sm text-foreground mb-2">点击上传或拖拽文件到这里</p>
            <p className="text-xs text-muted-foreground">支持 JPG、PNG、PDF 格式，最大10MB</p>
          </div>

          <div className="bg-secondary/50 rounded-xl p-4 mb-6">
            <h4 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-primary" />
              注意事项
            </h4>
            <ul className="text-xs text-muted-foreground space-y-1">
              <li>• 请确保上传的文件清晰可读</li>
              <li>• 敏感信息可以打码处理</li>
              <li>• 信息仅用于认证，不会对外展示</li>
            </ul>
          </div>

          <button
            onClick={() => setStep('field-pending')}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium"
          >
            提交审核
          </button>
        </div>
      </div>
    )
  }

  // Field pending
  if (step === 'field-pending') {
    return (
      <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3">
            <h1 className="font-medium text-foreground">提交成功</h1>
          </div>
        </header>

        <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
          <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
            <CheckCircle className="w-8 h-8 text-primary" />
          </div>

          <h2 className="font-serif text-xl text-foreground mb-3">材料已提交</h2>
          <p className="text-sm text-muted-foreground mb-2">
            感谢你的配合
          </p>
          <p className="text-sm text-muted-foreground mb-8">
            我们会在1-2个工作日内完成审核
          </p>

          <button
            onClick={onBack}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium"
          >
            返回
          </button>
        </div>
      </div>
    )
  }

  return null
}
