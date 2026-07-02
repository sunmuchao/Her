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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getErrorMessage } from '@/lib/api/errors'
import { ErrorState } from '@/components/her/ui/error-state'
import { FadeIn } from '@/components/her/ui/animations'
import UnifiedReviewWorkbench from '@/components/her/verification-review/unified-review-workbench'
import TaskDetailDrawer from '@/components/her/ops-workbench/task-detail-drawer'
import { useOpsWorkbenchSummary } from '@/hooks/use-ops-workbench'
import { usePageVisibility } from '@/hooks/use-page-visibility'

type OpsWorkbenchPageProps = {
  onBack?: () => void // 保留兼容性，但优先使用 router.back()
}

type WorkbenchTab = 'ops' | 'review'

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
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 页面可见性检测
  const isVisible = usePageVisibility()

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

  const openTaskDrawer = (taskId: string) => {
    setSelectedTaskId(taskId)
    setDrawerOpen(true)
  }

  const closeTaskDrawer = () => {
    setDrawerOpen(false)
    setSelectedTaskId(null)
  }

  const retryTask = async (taskId: string) => {
    // TODO: 调用实际API重试任务
    console.log('重试任务:', taskId)
    // 重试成功后关闭抽屉并刷新数据
    closeTaskDrawer()
    void loadSummary()
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
          message={getErrorMessage(loadError)}
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
          <div className="flex-1">
            <button type="button" onClick={() => router.back()} className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
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
                                onClick={() => openTaskDrawer(String(job.task_id || `task_${idx}`))}
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
          <div className="rounded-2xl border border-border/60 bg-card/50 p-4 text-xs text-muted-foreground">
            <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
              <ShieldAlert className="h-4 w-4" />
              接入说明
            </div>
            <p>读侧：GET /v1/ops/workbench/summary（聚合 async-jobs dashboard + ledger 预览）</p>
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
          taskId={selectedTaskId}
          onClose={closeTaskDrawer}
          onRetry={retryTask}
        />
      )}
    </div>
  )
}
