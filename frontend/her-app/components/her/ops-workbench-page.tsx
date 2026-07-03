'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Activity,
  ArrowLeft,
  AlertTriangle,
  Layers,
  RefreshCw,
  ShieldAlert,
  Workflow,
  FileCheck,
  ChevronDown,
  ChevronUp,
  Clock,
  Flag,
  Bug,
  Shield,
  BarChart3,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/api/errors'
import { ErrorState } from '@/components/her/ui/error-state'
import { FadeIn } from '@/components/her/ui/animations'
import UnifiedReviewWorkbench from '@/components/her/verification-review/unified-review-workbench'
import TaskDetailDrawer from '@/components/her/ops-workbench/task-detail-drawer'
import {
  useConversionViews,
  useFraudNetworks,
  useOpsAsyncJobDashboard,
  useOpsWorkbenchSummary,
  useRiskAppeals,
  useRiskCases,
  useRiskDashboard,
  useRiskReports,
} from '@/hooks/use-ops-workbench'
import { usePageVisibility } from '@/hooks/use-page-visibility'

type OpsWorkbenchPageProps = {
  onBack?: () => void // 保留兼容性，但优先使用 router.back()
}

type WorkbenchTab = 'ops' | 'review'

type TaskSelection = {
  taskId: string
  pollPath?: string | null
}

type StatCardProps = {
  label: string
  value: string | number
  alert?: boolean // 红色告警
  warning?: boolean // 黄色警告
  icon?: React.ReactNode
}

function StatCard({ label, value, alert, warning, icon }: StatCardProps) {
  return (
    <div
      className={cn(
        'rounded-2xl border p-4 shadow-sm transition-all',
        alert
          ? 'border-red-200/60 bg-red-50/50'
          : warning
          ? 'border-yellow-200/60 bg-yellow-50/50'
          : 'border-border/60 bg-card/80'
      )}
    >
      <div className="flex items-center gap-2">
        {icon && <span className="text-muted-foreground">{icon}</span>}
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
      <p
        className={cn(
          'mt-1 text-2xl font-semibold',
          alert ? 'text-red-600' : warning ? 'text-yellow-600' : 'text-foreground'
        )}
      >
        {value}
      </p>
    </div>
  )
}

export default function OpsWorkbenchPage({ onBack }: OpsWorkbenchPageProps) {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<WorkbenchTab>('ops')
  const [expandedSystems, setExpandedSystems] = useState<Record<string, boolean>>({})
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true)
  const [selectedTask, setSelectedTask] = useState<TaskSelection | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [conversionInput, setConversionInput] = useState('')
  const [conversionTarget, setConversionTarget] = useState('')

  // 页面可见性检测
  const isVisible = usePageVisibility()
  const handleBack = () => {
    if (onBack) {
      onBack()
      return
    }
    router.back()
  }

  // Ops Workbench 数据获取（React Query）
  const {
    data: summary,
    error: loadError,
    isLoading: loading,
    refetch: loadSummary,
  } = useOpsWorkbenchSummary({
    enabled: autoRefreshEnabled && activeTab === 'ops' && isVisible,
    refetchInterval: autoRefreshEnabled && activeTab === 'ops' && isVisible ? 30000 : false,
  })

  const { refetch: refetchAsyncDashboard } = useOpsAsyncJobDashboard({
    enabled: autoRefreshEnabled && activeTab === 'ops' && isVisible,
    refetchInterval: autoRefreshEnabled && activeTab === 'ops' && isVisible ? 30000 : false,
  })

  const { data: riskDashboard } = useRiskDashboard(7, activeTab === 'ops')
  const { data: riskCasesData, refetch: refetchRiskCases } = useRiskCases(8, activeTab === 'ops')
  const { data: riskReportsData, refetch: refetchRiskReports } = useRiskReports(8, activeTab === 'ops')
  const { data: fraudNetworksData, refetch: refetchFraudNetworks } = useFraudNetworks(8, activeTab === 'ops')
  const { data: riskAppealsData, refetch: refetchRiskAppeals } = useRiskAppeals(8, activeTab === 'ops')
  const {
    data: conversionViews,
    error: conversionError,
    isFetching: conversionLoading,
  } = useConversionViews(conversionTarget, Boolean(conversionTarget))

  const openTaskDrawer = (taskId: string, pollPath?: string | null) => {
    setSelectedTask({ taskId, pollPath })
    setDrawerOpen(true)
  }

  const closeTaskDrawer = () => {
    setDrawerOpen(false)
    setSelectedTask(null)
  }

  const retryTask = async (_taskId: string) => {
    closeTaskDrawer()
    void loadSummary()
    void refetchAsyncDashboard()
  }

  const toggleSystemExpanded = (system: string) => {
    setExpandedSystems((prev) => ({
      ...prev,
      [system]: !prev[system],
    }))
  }

  const dashboard = summary?.dashboard
  const totals = dashboard?.totals || {}
  const ledgerAvailable = dashboard?.ledger?.available === true
  const relations = summary?.relations_preview || []
  const riskCases = riskCasesData?.risk_cases || []
  const riskReports = riskReportsData?.reports || []
  const fraudNetworks = fraudNetworksData?.fraud_networks || []
  const riskAppeals = riskAppealsData?.appeals || []
  const riskSummary = (riskDashboard?.dashboard || {}) as Record<string, unknown>

  // 计算失败和积压数量
  const failedCount = totals.failed ?? 0
  const pendingCount = totals.pending ?? 0
  const processingCount = totals.processing ?? 0
  const succeededCount = totals.succeeded ?? 0
  const retryPendingCount = totals.retry_pending ?? 0

  // 计算总数
  const totalAll = totals.all ?? totals.total ?? (pendingCount + processingCount + succeededCount + failedCount + retryPendingCount)

  const hasFailedAlert = failedCount > 5
  const hasPendingWarning = pendingCount > 20

  const riskCaseCount =
    Number(riskSummary.open_case_count || riskSummary.case_count || riskCases.length || 0)
  const reportCount = Number(riskSummary.report_count || riskReports.length || 0)
  const fraudCount = Number(riskSummary.fraud_network_count || fraudNetworks.length || 0)
  const appealCount = Number(riskSummary.appeal_count || riskAppeals.length || 0)

  function renderCompactRows(
    items: Array<Record<string, unknown>>,
    fields: string[],
    emptyText: string,
  ) {
    if (!items.length) {
      return <p className="text-sm text-muted-foreground">{emptyText}</p>
    }
    return (
      <div className="space-y-2">
        {items.slice(0, 5).map((item, index) => (
          <div key={String(item.id || item.risk_case_id || item.report_id || item.appeal_id || index)} className="rounded-xl border border-border/40 px-3 py-2 text-xs">
            {fields.map((field) => (
              <p key={field} className={field === fields[0] ? 'font-medium text-foreground' : 'text-muted-foreground'}>
                {field}: {String(item[field] ?? '—')}
              </p>
            ))}
          </div>
        ))}
      </div>
    )
  }

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
        <button type="button" onClick={handleBack} className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground">
          <ArrowLeft className="h-4 w-4" />
          返回
        </button>
        <ErrorState
          title="无法打开运营工作台"
          message={getErrorMessage(loadError)}
          onRetry={() => void loadSummary()}
        />
      </div>
    )
  }

  return (
    <div className="min-h-screen pb-10">
      <div className="sticky top-0 z-20 border-b border-border/50 bg-background/90 backdrop-blur-md px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1">
            <button type="button" onClick={handleBack} className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
              <ArrowLeft className="h-3.5 w-3.5" />
              返回
            </button>
            <h1 className="font-serif text-xl text-foreground">
              {activeTab === 'ops' ? '红娘协作台' : '资料审核工作台'}
            </h1>
            {activeTab === 'ops' && (
              <p className="text-xs text-muted-foreground mt-1">§18 — 异步任务监控与关系漏斗追踪</p>
            )}
          </div>

          {/* Tab切换按钮 */}
          <div className="flex gap-1.5 bg-muted/30 rounded-xl p-1">
            <button
              type="button"
              onClick={() => setActiveTab('ops')}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                activeTab === 'ops'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Activity className="h-3.5 w-3.5 inline mr-1" />
              运营协作
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('review')}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                activeTab === 'review'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <FileCheck className="h-3.5 w-3.5 inline mr-1" />
              资料审核
            </button>
          </div>

          {/* 刷新按钮和自动刷新控制 */}
          <div className="flex items-center gap-2">
            {activeTab === 'ops' && autoRefreshEnabled && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                <span>自动刷新中</span>
              </div>
            )}
            <button
              type="button"
              onClick={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
              className={cn(
                'rounded-full border border-border p-2 transition-all',
                autoRefreshEnabled
                  ? 'text-primary hover:text-primary/80'
                  : 'text-muted-foreground hover:text-foreground'
              )}
              aria-label={autoRefreshEnabled ? '暂停自动刷新' : '开启自动刷新'}
              title={autoRefreshEnabled ? '自动刷新已开启（30秒）' : '自动刷新已暂停'}
            >
              <RefreshCw className={cn('h-4 w-4', autoRefreshEnabled && 'animate-spin')} />
            </button>
            <button
              type="button"
              onClick={() => void loadSummary()}
              className="rounded-full border border-border p-2 text-muted-foreground hover:text-foreground"
              aria-label="手动刷新"
              title="立即刷新"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* 根据Tab渲染不同内容 */}
      {activeTab === 'review' ? (
        <UnifiedReviewWorkbench />
      ) : (
        <div className="px-4 pt-4 space-y-6">
        {/* 第一层：核心指标卡片 */}
        <FadeIn>
          <div className="grid grid-cols-4 gap-3">
            <StatCard
              label="任务总数"
              value={totalAll}
              icon={<Activity className="h-4 w-4" />}
            />
            <StatCard
              label="失败任务"
              value={failedCount}
              alert={hasFailedAlert}
              icon={<AlertTriangle className="h-4 w-4" />}
            />
            <StatCard
              label="积压任务"
              value={pendingCount}
              warning={hasPendingWarning}
              icon={<Clock className="h-4 w-4" />}
            />
            <StatCard
              label="Ledger可用"
              value={ledgerAvailable ? '✓' : '✗'}
              icon={<Layers className="h-4 w-4" />}
            />
          </div>
          {hasFailedAlert && (
            <p className="text-xs text-red-600 mt-2">
              ⚠️ 失败任务超过5个，建议立即查看详情
            </p>
          )}
          {hasPendingWarning && (
            <p className="text-xs text-yellow-600 mt-1">
              ⏱️ 任务积压超过20个，系统可能繁忙
            </p>
          )}
        </FadeIn>

        {/* 第二层：子系统详情（可折叠） */}
        <FadeIn delay={0.05}>
          <div className="rounded-2xl border border-border/60 bg-card/70 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Activity className="h-4 w-4 text-primary" />
                子系统任务概览
              </div>
              <p className="text-xs text-muted-foreground">
                共 {Object.keys(dashboard?.systems || {}).length} 个子系统
              </p>
            </div>
            <div className="space-y-3">
              {Object.entries(dashboard?.systems || {}).map(([system, block]) => (
                <div key={system} className="rounded-xl bg-muted/30 px-3 py-2">
                  <button
                    type="button"
                    onClick={() => toggleSystemExpanded(system)}
                    className="w-full flex items-center justify-between text-sm"
                  >
                    <span className="font-medium capitalize">{system}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {block.summary?.pending ?? 0} 待处理
                      </span>
                      {expandedSystems[system] ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </button>
                  {expandedSystems[system] && block.summary && (
                    <div className="mt-2 pt-2 border-t border-border/40">
                      <div className="grid grid-cols-4 gap-2 text-xs text-muted-foreground">
                        {Object.entries(block.summary).map(([key, value]) => (
                          <div key={key} className="flex flex-col">
                            <span className="text-muted-foreground">{key}</span>
                            <span className="font-medium text-foreground">{value}</span>
                          </div>
                        ))}
                      </div>
                      {block.recent_jobs && block.recent_jobs.length > 0 && (
                        <div className="mt-2 pt-2 border-t border-border/40">
                          <p className="text-xs font-medium text-foreground mb-1">
                            最近任务（{block.recent_jobs.length}个）
                          </p>
                          <div className="max-h-32 overflow-y-auto space-y-1">
                            {block.recent_jobs.slice(0, 5).map((job, idx) => (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => openTaskDrawer(String(job.job_id || job.task_id || `task_${idx}`), String(job.poll_path || ''))}
                                className={cn(
                                  'w-full rounded-lg px-2 py-1 text-xs transition-all hover:shadow-sm',
                                  job.status === 'failed'
                                    ? 'bg-red-100 text-red-700 border border-red-200 hover:bg-red-200'
                                    : 'bg-muted/40 hover:bg-muted/60'
                                )}
                              >
                                <div className="flex items-center justify-between">
                                  <span className="font-medium">{job.task_id || `task_${idx}`}</span>
                                  <span className={cn(
                                    'ml-2',
                                    job.status === 'failed' ? 'text-red-700' : 'text-muted-foreground'
                                  )}>
                                    {job.status === 'failed' && '⚠️ '}
                                    {job.status || 'unknown'}
                                  </span>
                                </div>
                                {job.status === 'failed' && (
                                  <p className="mt-1 text-xs text-red-600 truncate">
                                    点击查看失败详情
                                  </p>
                                )}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={0.1}>
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="风险案件"
              value={riskCaseCount}
              warning={riskCaseCount > 0}
              icon={<Shield className="h-4 w-4" />}
            />
            <StatCard
              label="举报记录"
              value={reportCount}
              icon={<Flag className="h-4 w-4" />}
            />
            <StatCard
              label="诈骗网络"
              value={fraudCount}
              alert={fraudCount > 0}
              icon={<Bug className="h-4 w-4" />}
            />
            <StatCard
              label="待处理申诉"
              value={appealCount}
              warning={appealCount > 0}
              icon={<ShieldAlert className="h-4 w-4" />}
            />
          </div>
        </FadeIn>

        <FadeIn delay={0.12}>
          <div className="rounded-2xl border border-border/60 bg-card/70 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Shield className="h-4 w-4 text-primary" />
                风控 / 举报 / 诈骗网络后台
              </div>
              <button
                type="button"
                onClick={() => {
                  void refetchRiskCases()
                  void refetchRiskReports()
                  void refetchFraudNetworks()
                  void refetchRiskAppeals()
                }}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                刷新
              </button>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-medium text-foreground">风险案件</p>
                {renderCompactRows(riskCases as Array<Record<string, unknown>>, ['risk_case_id', 'status', 'recommended_action'], '暂无风险案件')}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-foreground">举报记录</p>
                {renderCompactRows(riskReports as Array<Record<string, unknown>>, ['report_id', 'report_type', 'reason_text'], '暂无举报记录')}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-foreground">诈骗网络</p>
                {renderCompactRows(fraudNetworks as Array<Record<string, unknown>>, ['subject_user_id', 'review_status', 'network_score'], '暂无诈骗网络样本')}
              </div>
              <div>
                <p className="mb-2 text-xs font-medium text-foreground">风险申诉</p>
                {renderCompactRows(riskAppeals as Array<Record<string, unknown>>, ['appeal_id', 'appeal_status', 'reason_text'], '暂无风险申诉')}
              </div>
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={0.14}>
          <div className="rounded-2xl border border-border/60 bg-card/70 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <BarChart3 className="h-4 w-4 text-primary" />
              订阅转化视图
            </div>
            <div className="flex gap-2">
              <input
                value={conversionInput}
                onChange={(event) => setConversionInput(event.target.value)}
                placeholder="输入 subscription_id"
                className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none"
              />
              <button
                type="button"
                onClick={() => setConversionTarget(conversionInput.trim())}
                className="rounded-xl bg-primary px-4 py-2 text-sm text-primary-foreground"
              >
                查询
              </button>
            </div>
            <div className="mt-3">
              {conversionLoading && <p className="text-sm text-muted-foreground">加载转化视图…</p>}
              {!conversionLoading && conversionError && (
                <p className="text-sm text-red-600">{getErrorMessage(conversionError)}</p>
              )}
              {!conversionLoading && !conversionError && conversionTarget && !(conversionViews?.length) && (
                <p className="text-sm text-muted-foreground">该订阅暂无转化数据</p>
              )}
              {!conversionLoading && Boolean(conversionViews?.length) && (
                <div className="space-y-2">
                  {conversionViews?.slice(0, 6).map((view, index) => (
                    <div key={`${view.recommendation_id || view.candidate_id || index}`} className="rounded-xl border border-border/40 px-3 py-2 text-xs">
                      <p className="font-medium text-foreground">
                        candidate #{String(view.candidate_id || '—')} · rec #{String(view.recommendation_id || '—')}
                      </p>
                      <p className="text-muted-foreground">
                        stage: {String(view.conversion_stage || view.recommendation_phase || '—')}
                      </p>
                      <p className="text-muted-foreground">
                        latest case: {String(view.latest_case_id || '—')} / {String(view.latest_case_status || '—')}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </FadeIn>

        <FadeIn delay={0.16}>
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

        <FadeIn delay={0.18}>
          <div className="rounded-2xl border border-border/60 bg-card/50 p-4 text-xs text-muted-foreground">
            <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
              <ShieldAlert className="h-4 w-4" />
              接入说明
            </div>
            <p>读侧：GET /v1/ops/workbench/summary（聚合 async-jobs dashboard + ledger 预览）</p>
            <p className="mt-1">任务详情：按 job 自带 `poll_path` 直连 `/v1/{target}/jobs/{job_id}`</p>
            <p className="mt-1">风控后台：`/v1/chat/risk-*`、`/v1/chat/reports`、`/v1/chat/fraud-networks`</p>
            <p className="mt-1 flex items-center gap-1">
              <Layers className="h-3.5 w-3.5" />
              Principal 由 Gateway 一次解析，避免各域重复 bind profile_id
            </p>
          </div>
        </FadeIn>
      </div>
      )}

      {/* 任务详情抽屉 */}
      {drawerOpen && (
        <TaskDetailDrawer
          taskId={selectedTask?.taskId || null}
          pollPath={selectedTask?.pollPath || null}
          onClose={closeTaskDrawer}
          onRetry={retryTask}
        />
      )}
    </div>
  )
}
