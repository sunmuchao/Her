'use client'

import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle,
  ChevronRight,
  Clock,
  FileText,
  Loader2,
  Shield,
  Upload,
  XCircle,
} from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface TrustCenterPageProps {
  runtimeContext: HerRuntimeContext
  onStartVerification: () => void
}

type TrustItem = {
  item_id: string
  title: string
  status?: string
  status_label?: string
  work_state?: string
  trigger_reasons?: string[]
  failure_reason?: string
  support_hint?: string
}

type NotificationItem = {
  title: string
  body?: string
  summary?: string
  created_at?: string
}

type TrustHubResponse = {
  trust_hub: {
    summary: {
      pending_verification_count: number
      pending_appeal_count: number
      active_risk_count: number
      notification_count: number
    }
    verification_center: { items: TrustItem[] }
    appeal_center: { items: TrustItem[] }
    risk_records: { items: TrustItem[] }
    notifications: NotificationItem[]
  }
}

export default function TrustCenterPage({
  runtimeContext,
  onStartVerification,
}: TrustCenterPageProps) {
  const [data, setData] = useState<TrustHubResponse['trust_hub'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function loadTrustHub() {
      if (!runtimeContext.userId) {
        setLoading(false)
        setError('缺少 user_id，当前无法读取信任中心。')
        return
      }

      setLoading(true)
      setError(null)
      try {
        const payload = await gatewayJson<TrustHubResponse>(
          `/v1/user-center/trust-hub${queryString({
            user_id: runtimeContext.userId,
            profile_id: runtimeContext.profileId,
          })}`,
        )
        if (!active) {
          return
        }
        setData(payload.trust_hub)
      } catch (err) {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : '信任中心加载失败')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadTrustHub()
    return () => {
      active = false
    }
  }, [runtimeContext.profileId, runtimeContext.userId])

  function statusIcon(workState?: string) {
    if (workState === 'complete') {
      return <CheckCircle className="w-5 h-5 text-green-600" />
    }
    if (workState === 'in_progress') {
      return <Clock className="w-5 h-5 text-gold" />
    }
    if (workState === 'action_required') {
      return <Upload className="w-5 h-5 text-primary" />
    }
    return <XCircle className="w-5 h-5 text-muted-foreground" />
  }

  return (
    <div className="flex flex-col h-full">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary to-rose flex items-center justify-center">
                <Shield className="w-5 h-5 text-primary-foreground" />
              </div>
              <div>
                <h1 className="editorial-title text-2xl text-foreground">信任中心</h1>
                <p className="text-xs text-muted-foreground">真实、透明、可追踪</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            正在同步信任中心
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : data ? (
          <>
            <section className="bg-gradient-to-br from-card via-card to-blush/30 rounded-3xl p-5 shadow-soft border border-rose-soft/30">
              <div className="flex items-center gap-4 mb-4">
                <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center">
                  <BadgeCheck className="w-7 h-7 text-green-600" />
                </div>
                <div>
                  <h2 className="text-lg font-medium text-foreground">当前信任状态</h2>
                  <p className="text-sm text-muted-foreground">
                    {data.summary.pending_verification_count} 个待验证事项 · {data.summary.pending_appeal_count} 个申诉事项
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2">
                {[
                  ['待验证', data.summary.pending_verification_count],
                  ['申诉中', data.summary.pending_appeal_count],
                  ['风险项', data.summary.active_risk_count],
                  ['通知', data.summary.notification_count],
                ].map(([label, value]) => (
                  <div key={String(label)} className="rounded-xl bg-background/70 p-3 text-center">
                    <p className="text-lg font-semibold text-foreground">{value}</p>
                    <p className="text-[10px] text-muted-foreground mt-1">{label}</p>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-foreground">认证中心</h2>
                <button onClick={onStartVerification} className="text-xs text-primary">
                  去处理
                </button>
              </div>
              <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
                {(data.verification_center.items || []).slice(0, 6).map((item, index, items) => (
                  <button
                    key={item.item_id}
                    onClick={onStartVerification}
                    className={`w-full px-4 py-4 flex items-start gap-3 text-left hover:bg-secondary/20 ${
                      index !== items.length - 1 ? 'border-b border-border/30' : ''
                    }`}
                  >
                    {statusIcon(item.work_state)}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
                        {item.status_label ? (
                          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {item.status_label}
                          </span>
                        ) : null}
                      </div>
                      {item.trigger_reasons?.length ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {item.trigger_reasons.slice(0, 2).join('；')}
                        </p>
                      ) : null}
                      {item.failure_reason ? (
                        <p className="mt-1 text-xs text-rose">{item.failure_reason}</p>
                      ) : null}
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground mt-1" />
                  </button>
                ))}
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-foreground">申诉中心</h2>
                <span className="text-xs text-muted-foreground">
                  {(data.appeal_center.items || []).length} 项
                </span>
              </div>
              <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
                {(data.appeal_center.items || []).slice(0, 4).map((item, index, items) => (
                  <div
                    key={item.item_id}
                    className={`px-4 py-4 flex items-start gap-3 ${
                      index !== items.length - 1 ? 'border-b border-border/30' : ''
                    }`}
                  >
                    <FileText className="w-5 h-5 text-primary mt-0.5" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
                        {item.status_label ? (
                          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {item.status_label}
                          </span>
                        ) : null}
                      </div>
                      {item.support_hint ? (
                        <p className="mt-1 text-xs text-muted-foreground">{item.support_hint}</p>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-foreground">风险记录</h2>
                <span className="text-xs text-muted-foreground">
                  {(data.risk_records.items || []).length} 条
                </span>
              </div>
              <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
                {(data.risk_records.items || []).slice(0, 4).map((item, index, items) => (
                  <div
                    key={item.item_id}
                    className={`px-4 py-4 flex items-start gap-3 ${
                      index !== items.length - 1 ? 'border-b border-border/30' : ''
                    }`}
                  >
                    <div className="w-8 h-8 rounded-full bg-rose-soft flex items-center justify-center">
                      <AlertTriangle className="w-4 h-4 text-rose" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
                        {item.status_label ? (
                          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {item.status_label}
                          </span>
                        ) : null}
                      </div>
                      {item.trigger_reasons?.length ? (
                        <p className="mt-1 text-xs text-muted-foreground">{item.trigger_reasons.join('；')}</p>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-foreground">通知</h2>
                <span className="text-xs text-muted-foreground">{data.notifications.length} 条</span>
              </div>
              <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
                {data.notifications.slice(0, 6).map((item, index) => (
                  <div
                    key={`${item.title}-${index}`}
                    className={`px-4 py-4 flex items-start gap-3 ${
                      index !== data.notifications.slice(0, 6).length - 1 ? 'border-b border-border/30' : ''
                    }`}
                  >
                    <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                      <FileText className="w-4 h-4 text-muted-foreground" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-foreground">{item.title}</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">{item.summary || item.body}</p>
                      {item.created_at ? (
                        <span className="text-[10px] text-muted-foreground/70 mt-1 block">{item.created_at}</span>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </div>
  )
}
