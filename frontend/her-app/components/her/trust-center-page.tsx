'use client'

import { Shield, AlertTriangle, FileText, ChevronRight, CheckCircle, XCircle, Upload, Clock, Loader2 } from 'lucide-react'
import { useTrustHub } from '@/lib/hooks/use-trust-hub'
import {
  mapTrustHubPendingActions,
  mapTrustHubVerificationItems,
  type VerificationItemView,
} from '@/lib/trust/map-trust-hub'
import { useMemo, useRef, useState } from 'react'
import { PageHeader } from './ui/page-header'
import { PageErrorState } from './ui/error-handling'
import { InlineEmpty } from './ui/empty-states'
import { TrustCenterPageSkeleton } from './ui/skeletons/trust-skeleton'

interface TrustCenterPageProps {
  onStartVerification: () => void
  onBack?: () => void
}

/**
 * 信任中心页面
 *
 * 使用 React Query hook 管理数据获取
 * 支持下拉刷新
 */
export default function TrustCenterPage({ onStartVerification, onBack }: TrustCenterPageProps) {
  const { data, isLoading, error, refetch, isFetching } = useTrustHub()

  // 下拉刷新状态
  const [pullDistance, setPullDistance] = useState(0)
  const [isPulling, setIsPulling] = useState(false)
  const touchStartY = useRef(0)

  // 解析数据
  const verificationItems = useMemo(
    () => mapTrustHubVerificationItems(data?.trust_hub?.verification_center?.items),
    [data],
  )
  const pendingItems = useMemo(
    () => mapTrustHubPendingActions(data?.trust_hub?.verification_center?.items),
    [data],
  )
  const riskRecords = useMemo(
    () =>
      (data?.trust_hub?.risk_records?.items || []).map((record, index) => ({
        id: String(index),
        title: record.title || '安全提醒',
        description: record.description || '',
        time: record.time || '',
        resolved: record.status === 'resolved',
      })),
    [data],
  )
  const notifications = useMemo(
    () =>
      (data?.trust_hub?.notifications || []).map((item, index) => ({
        id: String(index),
        title: item.title || '通知',
        description: item.body || '',
        time: item.created_at || '',
      })),
    [data],
  )
  const priorityItems = useMemo(() => {
    const priorityMap: Record<string, number> = {
      '活体视频认证': 0,
      '真人认证': 0,
      '身份认证': 1,
      '学历认证': 2,
      '职业认证': 3,
      '收入认证': 4,
    }

    return verificationItems
      .filter((item) => item.status === 'unverified')
      .sort((a, b) => {
        const aPriority = priorityMap[a.name] ?? 99
        const bPriority = priorityMap[b.name] ?? 99
        if (aPriority !== bPriority) return aPriority - bPriority
        return a.name.localeCompare(b.name, 'zh-CN')
      })
  }, [verificationItems])
  const reviewingItems = useMemo(
    () => verificationItems.filter((item) => item.status === 'pending'),
    [verificationItems],
  )
  const completedItems = useMemo(
    () => verificationItems.filter((item) => item.status === 'verified'),
    [verificationItems],
  )
  const summaryTitle = priorityItems.length > 0
    ? `还差 ${priorityItems.length} 项认证`
    : reviewingItems.length > 0
      ? '认证材料审核中'
      : completedItems.length > 0
        ? '已完成全部认证'
        : '开始建立你的认证'
  const summaryDescription = priorityItems.length > 0
    ? `推荐先完成：${priorityItems.slice(0, 2).map((item) => item.name).join('、')}`
    : reviewingItems.length > 0
      ? '你已提交部分材料，审核结果会在这里同步。'
      : completedItems.length > 0
        ? '你的资料可信度更高，关键信息已更完整。'
        : '完成认证后，资料会更容易被信任。'

  // 状态样式映射
  const getStatusStyles = (status: string) => {
    if (status === 'verified') return { bg: 'bg-primary/10', text: 'text-primary', icon: 'text-primary' }
    if (status === 'pending') return { bg: 'bg-gold/10', text: 'text-gold', icon: 'text-gold' }
    return { bg: 'bg-secondary', text: 'text-muted-foreground', icon: 'text-muted-foreground' }
  }

  const getStatusIcon = (status: string) => {
    const styles = getStatusStyles(status)
    if (status === 'verified') return <CheckCircle className={`w-5 h-5 ${styles.icon}`} />
    if (status === 'pending') return <Clock className={`w-5 h-5 ${styles.icon}`} />
    return <XCircle className={`w-5 h-5 ${styles.icon}`} />
  }

  const getStatusText = (status: string) => {
    if (status === 'verified') return '已认证'
    if (status === 'pending') return '审核中'
    return '未认证'
  }
  const getActionLabel = (item: VerificationItemView) => {
    if (item.status === 'pending') return '查看进度'
    if (item.name.includes('视频') || item.name.includes('真人')) return '开始认证'
    if (item.name.includes('学历')) return '上传学历材料'
    if (item.name.includes('职业')) return '上传职业材料'
    if (item.name.includes('收入')) return '上传收入材料'
    return '去认证'
  }

  // 下拉刷新处理
  const handleTouchStart = (e: React.TouchEvent) => {
    const scrollEl = e.currentTarget
    if (scrollEl.scrollTop <= 0) {
      touchStartY.current = e.touches[0].clientY
      setIsPulling(true)
    }
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isPulling) return
    const scrollEl = e.currentTarget
    if (scrollEl.scrollTop > 0) {
      setIsPulling(false)
      setPullDistance(0)
      return
    }
    const deltaY = e.touches[0].clientY - touchStartY.current
    if (deltaY > 0) {
      const distance = Math.max(0, Math.min(100, deltaY))
      setPullDistance(distance)
    } else {
      setPullDistance(0)
    }
  }

  const handleTouchEnd = () => {
    if (pullDistance > 60 && !isFetching) {
      void refetch()
    }
    setPullDistance(0)
    setIsPulling(false)
    touchStartY.current = 0
  }

  // 加载状态
  if (isLoading) {
    return <TrustCenterPageSkeleton />
  }

  // 错误状态 - 使用统一错误组件
  if (error) {
    return (
      <PageErrorState
        message={error instanceof Error ? error.message : '加载信任中心失败'}
        onRetry={() => void refetch()}
        variant="full"
      />
    )
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header - 使用统一组件 */}
      <PageHeader
        title="信任中心"
        subtitle="安全、透明、值得信赖"
        icon={<Shield className="w-5 h-5 text-primary" />}
        showBack={!!onBack}
        onBack={onBack}
      />

      <div
        className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* 下拉刷新指示器 */}
        <div
          className="flex items-center justify-center py-2 text-muted-foreground transition-all"
          style={{
            height: isFetching ? 40 : pullDistance,
            opacity: pullDistance > 0 || isFetching ? 1 : 0,
          }}
        >
          {isFetching ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : pullDistance > 60 ? (
            <span className="text-xs">释放刷新</span>
          ) : pullDistance > 0 ? (
            <span className="text-xs">下拉刷新</span>
          ) : null}
        </div>

        <section className="rounded-2xl border border-primary/15 bg-gradient-to-br from-primary/[0.08] via-background to-background p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
              <Shield className="w-5 h-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-primary mb-1">认证提醒</p>
              <h2 className="text-base font-medium">{summaryTitle}</h2>
              <p className="text-sm text-muted-foreground mt-1">{summaryDescription}</p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-medium mb-2">优先完成</h2>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {priorityItems.length === 0 ? (
              <InlineEmpty message="还没有认证记录，完成认证可提升可信度" />
            ) : (
              priorityItems.map((item, i) => {
                const styles = getStatusStyles(item.status)
                return (
                  <button
                    key={`${item.name}-${i}`}
                    onClick={onStartVerification}
                    className={`w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/50 ${
                      i !== priorityItems.length - 1 ? 'border-b border-border' : ''
                    }`}
                  >
                    {getStatusIcon(item.status)}
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{item.name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${styles.bg} ${styles.text}`}>
                          {getStatusText(item.status)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                    </div>
                    <div className="flex items-center gap-1 text-primary">
                      <span className="text-xs font-medium">{getActionLabel(item)}</span>
                      <ChevronRight className="w-4 h-4" />
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </section>

        {reviewingItems.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">审核中 / 待处理</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {reviewingItems.map((item, i) => {
                const styles = getStatusStyles(item.status)
                return (
                  <button
                    key={`${item.name}-pending-${i}`}
                    onClick={onStartVerification}
                    className={`w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/50 ${
                      i !== reviewingItems.length - 1 ? 'border-b border-border' : ''
                    }`}
                  >
                    {getStatusIcon(item.status)}
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{item.name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${styles.bg} ${styles.text}`}>
                          {getStatusText(item.status)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                    </div>
                    <div className="flex items-center gap-1 text-primary">
                      <span className="text-xs font-medium">{getActionLabel(item)}</span>
                      <ChevronRight className="w-4 h-4" />
                    </div>
                  </button>
                )
              })}
            </div>
          </section>
        )}

        {/* 待处理项 */}
        {pendingItems.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">待处理</h2>
            <div className="space-y-2">
              {pendingItems.map((item) => (
                <button
                  key={item.id}
                  onClick={onStartVerification}
                  className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-gold/10 flex items-center justify-center">
                      <Upload className="w-4 h-4 text-gold" />
                    </div>
                    <div className="flex-1">
                      <span className="text-sm font-medium">{item.title}</span>
                      <p className="text-xs text-muted-foreground">{item.description}</p>
                      <span className="text-[10px] text-gold">{item.dueDate}</span>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

        {completedItems.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">已完成</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {completedItems.map((item, i) => {
                const styles = getStatusStyles(item.status)
                return (
                  <div
                    key={`${item.name}-verified-${i}`}
                    className={`px-4 py-3 flex items-center gap-3 ${
                      i !== completedItems.length - 1 ? 'border-b border-border' : ''
                    }`}
                  >
                    {getStatusIcon(item.status)}
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{item.name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${styles.bg} ${styles.text}`}>
                          {getStatusText(item.status)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* 安全记录 */}
        {riskRecords.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">安全记录</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {riskRecords.map((record, i) => (
                <div
                  key={record.id}
                  className={`px-4 py-3 flex items-center gap-3 ${i !== riskRecords.length - 1 ? 'border-b border-border' : ''}`}
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${record.resolved ? 'bg-primary/10' : 'bg-rose/10'}`}>
                    <AlertTriangle className={`w-4 h-4 ${record.resolved ? 'text-primary' : 'text-rose'}`} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{record.title}</span>
                      {record.resolved && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">已处理</span>}
                    </div>
                    <p className="text-xs text-muted-foreground">{record.description}</p>
                    <span className="text-[10px] text-muted-foreground">{record.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 审核通知 */}
        {notifications.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">审核通知</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {notifications.map((n, i) => (
                <div
                  key={n.id}
                  className={`px-4 py-3 flex items-center gap-3 ${i !== notifications.length - 1 ? 'border-b border-border' : ''}`}
                >
                  <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                    <FileText className="w-4 h-4 text-muted-foreground" />
                  </div>
                  <div className="flex-1">
                    <span className="text-sm font-medium">{n.title}</span>
                    <p className="text-xs text-muted-foreground">{n.description}</p>
                    <span className="text-[10px] text-muted-foreground">{n.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 客服支持 */}
        <div className="bg-secondary rounded-xl p-4 text-center">
          <p className="text-sm text-muted-foreground mb-1">遇到问题？</p>
          <button className="text-sm text-primary font-medium">联系客服支持</button>
        </div>
      </div>
    </div>
  )
}
