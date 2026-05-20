'use client'

import { useEffect, useState } from 'react'
import { BadgeCheck, ChevronRight, Loader2, Settings, Shield, UserRound } from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface ProfilePageProps {
  runtimeContext: HerRuntimeContext
  onStartVerification: () => void
}

type TrustHubResponse = {
  trust_hub: {
    summary: {
      pending_verification_count: number
      pending_appeal_count: number
      active_risk_count: number
      notification_count: number
    }
  }
}

export default function ProfilePage({
  runtimeContext,
  onStartVerification,
}: ProfilePageProps) {
  const [summary, setSummary] = useState<TrustHubResponse['trust_hub']['summary'] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    async function loadSummary() {
      if (!runtimeContext.userId) {
        setLoading(false)
        return
      }
      try {
        const payload = await gatewayJson<TrustHubResponse>(
          `/v1/user-center/trust-hub${queryString({
            user_id: runtimeContext.userId,
            profile_id: runtimeContext.profileId,
            limit: 8,
          })}`,
        )
        if (active) {
          setSummary(payload.trust_hub.summary)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }
    loadSummary()
    return () => {
      active = false
    }
  }, [runtimeContext.profileId, runtimeContext.userId])

  return (
    <div className="flex flex-col h-full">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <h1 className="editorial-title text-2xl text-foreground">我的</h1>
            <p className="text-xs text-muted-foreground mt-0.5">我的婚恋资料与信任状态</p>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        <section className="rounded-3xl bg-gradient-to-br from-card via-card to-blush/30 p-5 border border-border/40 shadow-soft">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-rose-soft/50">
              <UserRound className="h-8 w-8 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-medium text-foreground">
                用户 {runtimeContext.userId || runtimeContext.requesterId || '未配置'}
              </h2>
              <p className="text-sm text-muted-foreground">
                profile_id: {runtimeContext.profileId || '未配置'}
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl bg-card p-5 border border-border/40 shadow-soft">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-foreground">信任摘要</h3>
            {loading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
          </div>
          {summary ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-secondary/50 p-3">
                <p className="text-lg font-semibold text-foreground">{summary.pending_verification_count}</p>
                <p className="text-xs text-muted-foreground mt-1">待验证</p>
              </div>
              <div className="rounded-xl bg-secondary/50 p-3">
                <p className="text-lg font-semibold text-foreground">{summary.notification_count}</p>
                <p className="text-xs text-muted-foreground mt-1">通知</p>
              </div>
              <div className="rounded-xl bg-secondary/50 p-3">
                <p className="text-lg font-semibold text-foreground">{summary.pending_appeal_count}</p>
                <p className="text-xs text-muted-foreground mt-1">申诉事项</p>
              </div>
              <div className="rounded-xl bg-secondary/50 p-3">
                <p className="text-lg font-semibold text-foreground">{summary.active_risk_count}</p>
                <p className="text-xs text-muted-foreground mt-1">风险记录</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              当前尚未拿到用户侧信任摘要，请确认 `user_id` 和 `profile_id` 配置。
            </p>
          )}
        </section>

        <section className="space-y-3">
          <button
            onClick={onStartVerification}
            className="w-full rounded-2xl border border-border/40 bg-card p-4 text-left shadow-soft"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-soft/40">
                <BadgeCheck className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">去完成认证与补件</p>
                <p className="text-xs text-muted-foreground mt-1">进入活体视频、字段核验与申诉流程。</p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </div>
          </button>

          <div className="rounded-2xl border border-border/40 bg-card p-4 text-left shadow-soft">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
                <Shield className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">资料与偏好入口</p>
                <p className="text-xs text-muted-foreground mt-1">
                  当前子应用已先接入 discovery、推荐、聊天和 trust hub，资料编辑可继续在此页扩展。
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border/40 bg-card p-4 text-left shadow-soft">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
                <Settings className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">联调信息</p>
                <p className="text-xs text-muted-foreground mt-1">
                  requester_id={runtimeContext.requesterId || '未配置'}，user_id={runtimeContext.userId || '未配置'}
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
