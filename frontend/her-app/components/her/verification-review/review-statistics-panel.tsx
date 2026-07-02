'use client'

import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Clock, CheckCircle, XCircle, AlertTriangle, BarChart3 } from 'lucide-react'
import { FadeIn } from '@/components/her/ui/animations'
import { fetchReviewStatistics, type ReviewStatistics } from '@/lib/api/endpoints/review-statistics'
import { getErrorMessage } from '@/lib/api/errors'

function StatCard({ label, value, icon, trend, color }: {
  label: string
  value: string | number
  icon: React.ReactNode
  trend?: 'up' | 'down'
  color?: string
}) {
  return (
    <div className="rounded-xl border border-border/60 bg-card/70 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground">{label}</span>
        <div className={color || 'text-primary'}>{icon}</div>
      </div>
      <div className="flex items-center justify-between">
        <p className="text-xl font-semibold text-foreground">{value}</p>
        {trend && (
          <div className={trend === 'up' ? 'text-green-600' : 'text-rose'}>
            {trend === 'up' ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ReviewStatisticsPanel() {
  const [statistics, setStatistics] = useState<ReviewStatistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReviewStatistics()
      .then((data) => setStatistics(data))
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="px-4 py-4">
        <div className="text-sm text-muted-foreground">加载统计数据...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="px-4 py-4">
        <div className="text-sm text-muted-foreground">{error}</div>
      </div>
    )
  }

  if (!statistics) {
    return null
  }

  const approveRate = statistics.approve_rate ? `${Math.round(statistics.approve_rate * 100)}%` : '—'
  const avgTime = statistics.average_review_time_minutes ? `${statistics.average_review_time_minutes}分钟` : '—'

  return (
    <FadeIn>
      <div className="px-4 py-4 border-b border-border/50">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground mb-4">
          <BarChart3 className="h-4 w-4" />
          审核统计概览
        </div>

        {/* 今日统计 */}
        <div className="mb-4">
          <p className="text-xs text-muted-foreground mb-2">今日审核</p>
          <div className="grid grid-cols-3 gap-2">
            <StatCard
              label="审核总数"
              value={statistics.today_reviews || 0}
              icon={<Clock className="w-4 h-4" />}
              color="text-primary"
            />
            <StatCard
              label="通过"
              value={statistics.today_approve || 0}
              icon={<CheckCircle className="w-4 h-4" />}
              color="text-green-600"
            />
            <StatCard
              label="驳回"
              value={statistics.today_reject || 0}
              icon={<XCircle className="w-4 h-4" />}
              color="text-rose"
            />
          </div>
        </div>

        {/* 总体统计 */}
        <div className="mb-4">
          <p className="text-xs text-muted-foreground mb-2">总体统计</p>
          <div className="grid grid-cols-2 gap-2">
            <StatCard
              label="通过率"
              value={approveRate}
              icon={<TrendingUp className="w-4 h-4" />}
              color="text-green-600"
              trend={statistics.approve_rate > 0.7 ? 'up' : undefined}
            />
            <StatCard
              label="平均审核时长"
              value={avgTime}
              icon={<Clock className="w-4 h-4" />}
              color="text-muted-foreground"
            />
          </div>
        </div>

        {/* 分类统计 */}
        <div className="grid grid-cols-4 gap-2">
          <div className="rounded-lg bg-green-500/10 border border-green-500/30 p-3 text-center">
            <CheckCircle className="w-4 h-4 mx-auto text-green-600 mb-1" />
            <p className="text-xs text-muted-foreground">已通过</p>
            <p className="text-sm font-semibold text-foreground">{statistics.approve_count || 0}</p>
          </div>
          <div className="rounded-lg bg-rose/10 border border-rose/30 p-3 text-center">
            <XCircle className="w-4 h-4 mx-auto text-rose mb-1" />
            <p className="text-xs text-muted-foreground">已驳回</p>
            <p className="text-sm font-semibold text-foreground">{statistics.reject_count || 0}</p>
          </div>
          <div className="rounded-lg bg-orange-500/10 border border-orange-500/30 p-3 text-center">
            <AlertTriangle className="w-4 h-4 mx-auto text-orange-600 mb-1" />
            <p className="text-xs text-muted-foreground">需补件</p>
            <p className="text-sm font-semibold text-foreground">{statistics.resubmission_count || 0}</p>
          </div>
          <div className="rounded-lg bg-muted/30 border border-border/40 p-3 text-center">
            <Clock className="w-4 h-4 mx-auto text-muted-foreground mb-1" />
            <p className="text-xs text-muted-foreground">待审核</p>
            <p className="text-sm font-semibold text-foreground">{statistics.pending_count || 0}</p>
          </div>
        </div>
      </div>
    </FadeIn>
  )
}