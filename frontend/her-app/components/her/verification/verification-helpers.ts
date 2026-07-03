import {
  parseGatewayUtcTimestamp,
  type LiveVideoChallenge,
  type VerificationNotification,
  type VerificationSubmission,
} from '@/lib/api/endpoints/verification'

export const VIDEO_RECORDING_SECONDS = 6

const ACTION_LABELS: Record<string, string> = {
  blink: '眨眼',
  open_mouth: '张嘴',
  turn_left: '向左转头',
  turn_right: '向右转头',
  nod_up: '抬头',
}

export function getActionLabel(action?: string) {
  const key = String(action || '').trim()
  return ACTION_LABELS[key] || key || '按提示完成动作'
}

export function formatChallengeDeadline(expiresAt?: string) {
  if (!expiresAt) return '本次 challenge 未返回有效期'

  const expiresAtMs = parseGatewayUtcTimestamp(expiresAt)
  const date = new Date(expiresAtMs)
  if (Number.isNaN(date.getTime())) return 'challenge 有效期解析失败'

  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getChallengeRemainingSeconds(expiresAt?: string, nowMs = Date.now()) {
  if (!expiresAt) return null
  const expiresAtMs = parseGatewayUtcTimestamp(expiresAt)
  if (Number.isNaN(expiresAtMs)) return null
  return Math.max(0, Math.ceil((expiresAtMs - nowMs) / 1000))
}

export function formatRemainingTime(totalSeconds: number | null) {
  if (totalSeconds === null) return '未返回倒计时'
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function buildGuideSteps(challenge: LiveVideoChallenge | null) {
  const promptSteps =
    challenge?.prompt_steps?.map((step) => ({
      key: step.action_key || step.spoken_code || `step-${step.step_index}`,
      title:
        step.label ||
        (step.kind === 'spoken_code' ? `读出数字 ${step.spoken_code || challenge?.spoken_code || ''}` : getActionLabel(step.action_key)),
      instruction:
        step.instruction ||
        (step.kind === 'spoken_code'
          ? `请大声读出数字 ${step.spoken_code || challenge?.spoken_code || ''}`
          : `请${step.label || getActionLabel(step.action_key)}`),
      kind: (step.kind || 'action') as 'action' | 'spoken_code',
    })) || []

  if (promptSteps.length > 0) {
    return promptSteps
  }

  const requiredActionSteps =
    challenge?.required_actions?.map((action, index) => ({
      key: action || `action-${index + 1}`,
      title: getActionLabel(action),
      instruction: `请${getActionLabel(action)}`,
      kind: 'action' as const,
    })) || []

  const spokenSteps = challenge?.spoken_code
    ? [
        {
          key: 'spoken-code',
          title: `读出数字 ${challenge.spoken_code}`,
          instruction: `请大声读出数字 ${challenge.spoken_code}`,
          kind: 'spoken_code' as const,
        },
      ]
    : []

  return [...requiredActionSteps, ...spokenSteps]
}

export function getGuidedRecordingState(params: {
  challenge: LiveVideoChallenge | null
  recordingTime: number
  totalDurationSeconds?: number
}) {
  const steps = buildGuideSteps(params.challenge)
  const totalDuration = params.totalDurationSeconds || VIDEO_RECORDING_SECONDS

  if (steps.length === 0) {
    return {
      steps,
      currentIndex: 0,
      currentStep: null,
      nextStep: null,
      progress: Math.min(100, Math.round((params.recordingTime / totalDuration) * 100)),
    }
  }

  const slotSize = totalDuration / steps.length
  const currentIndex = Math.min(steps.length - 1, Math.floor(params.recordingTime / Math.max(slotSize, 1)))
  const currentStep = steps[currentIndex] || null
  const nextStep = steps[currentIndex + 1] || null
  const progress = Math.min(100, Math.round((params.recordingTime / totalDuration) * 100))

  return {
    steps,
    currentIndex,
    currentStep,
    nextStep,
    progress,
  }
}

export function getVideoStatusPresentation(params: {
  submission?: VerificationSubmission | null
  notification?: VerificationNotification | null
}) {
  const status = String(params.submission?.status || '').toLowerCase()
  const hint = params.notification?.body || params.submission?.recommended_next_step || ''

  if (status === 'approved') {
    return {
      tone: 'success' as const,
      title: '认证通过',
      summary: hint || '你的身份认证已通过，认证标识会自动同步到资料页。',
      ctaLabel: '返回资料页',
    }
  }

  if (status === 'resubmission_required') {
    return {
      tone: 'warning' as const,
      title: '需要重新录制',
      summary: hint || '本次视频需要补录，请按最新提示重新完成 challenge。',
      ctaLabel: '重新开始',
    }
  }

  if (status === 'rejected') {
    return {
      tone: 'danger' as const,
      title: '认证未通过',
      summary: hint || '审核未通过，请根据提示补充材料后再次提交。',
      ctaLabel: '重新开始',
    }
  }

  return {
    tone: 'pending' as const,
    title: '审核中',
    summary: hint || '材料已进入审核队列，系统会先完成机器预审，再视情况转人工复核。',
    ctaLabel: '返回资料页',
  }
}

export function getConfidenceLabel(confidenceBand?: string) {
  const text = String(confidenceBand || '').trim()
  if (!text) return null
  if (text === 'high') return '机器判断把握较高'
  if (text === 'medium') return '机器判断把握中等'
  if (text === 'low') return '机器判断把握较低'
  return text
}
