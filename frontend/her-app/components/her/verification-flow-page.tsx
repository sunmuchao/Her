'use client'

import { useEffect, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  Camera,
  ChevronRight,
  Clock,
  Loader2,
  Upload,
} from 'lucide-react'

import { gatewayJson } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface VerificationFlowPageProps {
  runtimeContext: HerRuntimeContext
  onBack: () => void
}

type TrustHubResponse = {
  trust_hub: {
    verification_center: {
      items: Array<{
        item_id: string
        title: string
        status_label?: string
        trigger_reasons?: string[]
      }>
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

export default function VerificationFlowPage({
  runtimeContext,
  onBack,
}: VerificationFlowPageProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<TrustHubResponse['trust_hub']['verification_center']['items']>([])
  const [challenge, setChallenge] = useState<ChallengeResponse['challenge'] | null>(null)
  const [challengeLoading, setChallengeLoading] = useState(false)

  useEffect(() => {
    let active = true
    async function loadVerificationItems() {
      if (!runtimeContext.userId) {
        setLoading(false)
        setError('缺少 user_id，当前无法读取认证事项。')
        return
      }
      try {
        const payload = await gatewayJson<TrustHubResponse>(
          `/v1/user-center/trust-hub?user_id=${runtimeContext.userId}${runtimeContext.profileId ? `&profile_id=${runtimeContext.profileId}` : ''}`,
        )
        if (active) {
          setItems(payload.trust_hub.verification_center.items || [])
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : '认证事项读取失败')
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }
    loadVerificationItems()
    return () => {
      active = false
    }
  }, [runtimeContext.profileId, runtimeContext.userId])

  async function createChallenge() {
    if (!runtimeContext.userId || !runtimeContext.profileId) {
      setError('活体 challenge 需要 user_id 和 profile_id。')
      return
    }
    setChallengeLoading(true)
    setError(null)
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
            <h1 className="font-medium text-foreground">认证与补件</h1>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-6 space-y-5">
        <section className="rounded-3xl bg-gradient-to-br from-card to-blush/20 p-5 border border-border/40 shadow-soft">
          <h2 className="editorial-title text-2xl text-foreground">认证中心</h2>
          <p className="mt-2 text-sm leading-6 text-taupe">
            这一页已经接到真实的 trust hub 认证事项，并且可以直接向后端创建活体视频 challenge。
            浏览器端真实录像上传和文件上传还需要结合实际 OSS / 媒体采集继续补齐。
          </p>
        </section>

        {loading ? (
          <div className="flex items-center justify-center rounded-2xl bg-card p-10 text-muted-foreground shadow-soft border border-border/30">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            正在同步认证事项
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <section className="space-y-3">
          <button
            onClick={createChallenge}
            disabled={challengeLoading}
            className="w-full rounded-2xl border border-rose-soft/40 bg-gradient-to-r from-blush/50 to-card p-4 text-left shadow-soft"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-rose-soft/60">
                {challengeLoading ? (
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                ) : (
                  <Camera className="h-5 w-5 text-primary" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">创建活体视频 challenge</p>
                <p className="text-xs text-muted-foreground mt-1">
                  从真实后端拉取动作挑战与 challenge phrase，供前端录像页接入。
                </p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </button>

          {challenge ? (
            <div className="rounded-2xl border border-border/40 bg-card p-4 shadow-soft">
              <p className="text-sm font-medium text-foreground">当前 challenge</p>
              <p className="mt-2 text-sm text-taupe">{challenge.challenge_phrase || '未返回 challenge_phrase'}</p>
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
                        {item.status_label ? (
                          <span className="rounded bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                            {item.status_label}
                          </span>
                        ) : null}
                      </div>
                      {item.trigger_reasons?.length ? (
                        <p className="mt-2 text-xs text-muted-foreground">
                          {item.trigger_reasons.join('；')}
                        </p>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <div className="rounded-2xl bg-secondary/60 p-4 text-xs text-muted-foreground flex items-start gap-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          字段核验真实文件上传、活体视频录制与 base64 提交还需要继续接浏览器媒体采集与上传链路；这版先把真实 challenge 和待处理事项接进来了。
        </div>
      </div>
    </div>
  )
}
