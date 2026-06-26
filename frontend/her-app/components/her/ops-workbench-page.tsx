'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  ArrowLeft,
  ClipboardCheck,
  Layers,
  RefreshCw,
  ShieldAlert,
  Workflow,
} from 'lucide-react'
import { getErrorMessage } from '@/lib/api/errors'
import {
  fetchOpsWorkbenchSummary,
  submitOpsOverride,
  type OpsWorkbenchSummary,
} from '@/lib/api/endpoints/ops'
import {
  fetchActiveRuleConfig,
  fetchExperimentBucketMembers,
  fetchRecommendationDecisionTrace,
  upsertExperimentBucketMember,
  type DecisionTrace,
  type RuleConfigActiveItem,
} from '@/lib/api/endpoints/rule-config'
import { ErrorState } from '@/components/her/ui/error-state'
import { FadeIn } from '@/components/her/ui/animations'

type OpsWorkbenchPageProps = {
  onBack?: () => void // 保留兼容性，但优先使用 router.back()
}

const RECOMMENDATION_ACTIONS = ['skip', 'save', 'direct_greet'] as const

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-card/80 p-4 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
    </div>
  )
}

export default function OpsWorkbenchPage({ onBack }: OpsWorkbenchPageProps) {
  const router = useRouter()
  const [summary, setSummary] = useState<OpsWorkbenchSummary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)
  const [recommendationId, setRecommendationId] = useState('')
  const [action, setAction] = useState<(typeof RECOMMENDATION_ACTIONS)[number]>('save')
  const [reason, setReason] = useState('')
  const [activeRules, setActiveRules] = useState<RuleConfigActiveItem[]>([])
  const [experimentMembers, setExperimentMembers] = useState<
    Array<{ profile_id: number; bucket_key: string }>
  >([])
  const [ruleConfigMessage, setRuleConfigMessage] = useState<string | null>(null)
  const [traceRecommendationId, setTraceRecommendationId] = useState('')
  const [decisionTrace, setDecisionTrace] = useState<DecisionTrace | null>(null)
  const [bucketProfileId, setBucketProfileId] = useState('')
  const [bucketKey, setBucketKey] = useState('exp_gate_score_55')

  const loadRuleConfig = useCallback(async () => {
    try {
      const [active, members] = await Promise.all([
        fetchActiveRuleConfig(),
        fetchExperimentBucketMembers(20),
      ])
      setActiveRules(active.active || [])
      setExperimentMembers(members.members || [])
    } catch (error) {
      setRuleConfigMessage(getErrorMessage(error, '规则配置加载失败'))
    }
  }, [])

  const loadSummary = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const data = await fetchOpsWorkbenchSummary(5)
      setSummary(data)
    } catch (error) {
      setLoadError(getErrorMessage(error))
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSummary()
    void loadRuleConfig()
  }, [loadSummary, loadRuleConfig])

  const handleSubmitOverride = async () => {
    if (!recommendationId.trim()) {
      setSubmitMessage('请填写 recommendation_id')
      return
    }
    setSubmitting(true)
    setSubmitMessage(null)
    try {
      const result = await submitOpsOverride({
        target_owner: 'recommendation',
        target_id: recommendationId.trim(),
        action,
        reason: reason.trim() || undefined,
      })
      setSubmitMessage(result.ok ? '运营 override 已提交' : '提交完成，请查看返回结果')
      void loadSummary()
    } catch (error) {
      setSubmitMessage(getErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  const dashboard = summary?.dashboard
  const totals = dashboard?.totals || {}
  const ledgerAvailable = dashboard?.ledger?.available === true
  const relations = summary?.relations_preview || []

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        加载运营台…
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="min-h-screen p-6">
        <button type="button" onClick={() => router.back()} className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground">
          <ArrowLeft className="h-4 w-4" />
          返回
        </button>
        <ErrorState
          title="无法打开运营工作台"
          message={loadError}
          onRetry={() => void loadSummary()}
        />
        <p className="mt-4 text-xs text-muted-foreground">
          需要 ops_operator / risk_reviewer / platform_admin 角色；本地联调可使用 Gateway legacy API key。
        </p>
      </div>
    )
  }

  return (
    <div className="min-h-screen pb-10">
      <div className="sticky top-0 z-20 border-b border-border/50 bg-background/90 backdrop-blur-md px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <button type="button" onClick={() => router.back()} className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
              <ArrowLeft className="h-3.5 w-3.5" />
              返回
            </button>
            <h1 className="font-serif text-xl text-foreground">红娘协作台</h1>
            <p className="text-xs text-muted-foreground mt-1">§14.3 — 异步任务、关系漏斗与推荐人工介入</p>
          </div>
          <button
            type="button"
            onClick={() => void loadSummary()}
            className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground"
            aria-label="刷新"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="px-4 pt-4 space-y-6">
        <FadeIn>
          <div className="grid grid-cols-2 gap-3">
            <StatCard label="异步任务总数" value={totals.all ?? totals.total ?? '—'} />
            <StatCard label="Ledger 可用" value={ledgerAvailable ? '是' : '否'} />
          </div>
        </FadeIn>

        <FadeIn delay={0.05}>
          <div className="rounded-2xl border border-border/60 bg-card/70 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Activity className="h-4 w-4 text-primary" />
              子系统任务概览
            </div>
            <div className="space-y-3">
              {Object.entries(dashboard?.systems || {}).map(([system, block]) => (
                <div key={system} className="rounded-xl bg-muted/30 px-3 py-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium capitalize">{system}</span>
                    <span className="text-xs text-muted-foreground">
                      recent {block.recent_jobs?.length ?? 0}
                    </span>
                  </div>
                  {block.summary && (
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      {Object.entries(block.summary).slice(0, 4).map(([key, value]) => (
                        <span key={key}>
                          {key}: {value}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={0.1}>
          <div className="rounded-2xl border border-border/60 bg-card/70 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Workflow className="h-4 w-4 text-primary" />
              关系漏斗预览
            </div>
            {relations.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无关系记录预览</p>
            ) : (
              <div className="space-y-2">
                {relations.slice(0, 6).map((relation, index) => (
                  <p
                    key={String(relation.relation_key || relation.case_id || index)}
                    className="rounded-xl border border-border/40 px-3 py-2 text-xs"
                  >
                    <span className="font-medium block">{String(relation.relation_key || '—')}</span>
                    <span className="text-muted-foreground mt-1 block">
                      stage: {String(relation.stage || relation.status || '—')}
                    </span>
                  </p>
                ))}
              </div>
            )}
          </div>
        </FadeIn>

        <FadeIn delay={0.15}>
          <div className="rounded-2xl border border-rose-200/60 bg-rose-soft/20 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <ClipboardCheck className="h-4 w-4 text-primary" />
              推荐人工 Override
            </div>
            <div className="space-y-3">
              <label className="block text-xs text-muted-foreground">
                recommendation_id
                <input
                  value={recommendationId}
                  onChange={(event) => setRecommendationId(event.target.value)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                  placeholder="例如 12345"
                />
              </label>
              <label className="block text-xs text-muted-foreground">
                action
                <select
                  value={action}
                  onChange={(event) => setAction(event.target.value as (typeof RECOMMENDATION_ACTIONS)[number])}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                >
                  {RECOMMENDATION_ACTIONS.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-xs text-muted-foreground">
                reason（可选）
                <textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm min-h-[72px]"
                />
              </label>
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleSubmitOverride()}
                className="w-full rounded-xl bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-60"
              >
                {submitting ? '提交中…' : '提交 OpsOverride'}
              </button>
              {submitMessage && <p className="text-xs text-muted-foreground">{submitMessage}</p>}
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={0.2}>
          <div className="rounded-2xl border border-border/60 bg-card/70 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Layers className="h-4 w-4 text-primary" />
              规则配置（§13.5）
            </div>
            <div className="space-y-3 text-xs">
              {activeRules.length === 0 ? (
                <p className="text-muted-foreground">暂无 global active 规则切片</p>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {activeRules.map((item) => (
                    <div key={`${item.slice_id}-${item.version_id}`} className="rounded-lg bg-muted/30 px-3 py-2">
                      <p className="font-medium text-foreground">{item.slice_id}</p>
                      <p className="text-muted-foreground">version: {item.version_id}</p>
                    </div>
                  ))}
                </div>
              )}
              <div className="border-t border-border/50 pt-3">
                <p className="font-medium text-foreground mb-2">实验桶成员</p>
                {experimentMembers.length === 0 ? (
                  <p className="text-muted-foreground">暂无 profile → bucket 映射</p>
                ) : (
                  <ul className="space-y-1 text-muted-foreground">
                    {experimentMembers.slice(0, 8).map((member) => (
                      <li key={member.profile_id}>
                        profile {member.profile_id} → {member.bucket_key}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <input
                    value={bucketProfileId}
                    onChange={(event) => setBucketProfileId(event.target.value)}
                    placeholder="profile_id"
                    className="rounded-lg border border-border bg-background px-2 py-1.5"
                  />
                  <input
                    value={bucketKey}
                    onChange={(event) => setBucketKey(event.target.value)}
                    placeholder="bucket_key"
                    className="rounded-lg border border-border bg-background px-2 py-1.5"
                  />
                </div>
                <button
                  type="button"
                  className="mt-2 w-full rounded-lg border border-border py-2 text-sm"
                  onClick={() => {
                    const profileId = Number(bucketProfileId)
                    if (!profileId || !bucketKey.trim()) {
                      setRuleConfigMessage('请填写 profile_id 与 bucket_key')
                      return
                    }
                    void upsertExperimentBucketMember({ profile_id: profileId, bucket_key: bucketKey.trim() })
                      .then(() => {
                        setRuleConfigMessage('实验桶成员已更新')
                        return loadRuleConfig()
                      })
                      .catch((error) => setRuleConfigMessage(getErrorMessage(error)))
                  }}
                >
                  保存实验桶映射
                </button>
              </div>
              <div className="border-t border-border/50 pt-3">
                <p className="font-medium text-foreground mb-2">推荐决策链</p>
                <div className="flex gap-2">
                  <input
                    value={traceRecommendationId}
                    onChange={(event) => setTraceRecommendationId(event.target.value)}
                    placeholder="recommendation_id"
                    className="flex-1 rounded-lg border border-border bg-background px-2 py-1.5"
                  />
                  <button
                    type="button"
                    className="rounded-lg border border-border px-3 py-1.5"
                    onClick={() => {
                      const id = traceRecommendationId.trim()
                      if (!id) return
                      void fetchRecommendationDecisionTrace(id)
                        .then((payload) => setDecisionTrace(payload.decision_trace || null))
                        .catch((error) => setRuleConfigMessage(getErrorMessage(error)))
                    }}
                  >
                    查询
                  </button>
                </div>
                {decisionTrace && (
                  <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-muted/40 p-2 text-[10px]">
                    {JSON.stringify(decisionTrace, null, 2)}
                  </pre>
                )}
              </div>
              {ruleConfigMessage && <p className="text-muted-foreground">{ruleConfigMessage}</p>}
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={0.25}>
          <div className="rounded-2xl border border-border/60 bg-card/50 p-4 text-xs text-muted-foreground">
            <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
              <ShieldAlert className="h-4 w-4" />
              接入说明
            </div>
            <p>读侧：GET /v1/ops/workbench/summary（聚合 async-jobs dashboard + ledger 预览）</p>
            <p className="mt-1">写侧：POST /v1/ops/overrides → recommendation owner API</p>
            <p className="mt-1 flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              Principal 由 Gateway 一次解析，避免各域重复 bind profile_id
            </p>
          </div>
        </FadeIn>
      </div>
    </div>
  )
}
