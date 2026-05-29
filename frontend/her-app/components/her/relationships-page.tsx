'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, BadgeCheck, ChevronRight, Loader2, MailOpen, Pin, Trash2, X } from 'lucide-react'
import Image from 'next/image'
import { fetchRelationshipsUnreadSummary } from '@/lib/api/endpoints/chat'
import { fetchTrustHub } from '@/lib/api/endpoints/trust-hub'
import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import {
  fetchMyProxyIntroCases,
  openProxyIntroChat,
  replyProxyIntroCase,
  type ProxyIntroCase,
} from '@/lib/api/endpoints/proxy-intro'
import { getErrorMessage } from '@/lib/api/errors'
import { canUseMockFallback } from '@/lib/mock'
import { logDataProvenance, usePageDataSource } from '@/lib/data-provenance'
import { getProfileId, getUserId, patchSessionContext } from '@/lib/auth/session'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'
import { mapTrustHubPendingActions } from '@/lib/trust/map-trust-hub'
import type { ChatUserInfo } from '@/hooks/use-app-router'
import type { CandidatePreview } from '@/lib/types/candidate'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { EmptyRelationships } from './ui/empty-states'
import { RelationshipsPageSkeleton } from './ui/skeletons'

interface RelationshipsPageProps {
  onOpenChat: (chatId: string, info?: ChatUserInfo) => void
  onStartVerification: () => void
  onNavigateToDiscover?: () => void
  onViewCandidate?: (candidateId: string, candidate?: CandidatePreview) => void
}

type PendingAction = {
  id: string
  type: 'verification'
  title: string
  description: string
  icon: typeof BadgeCheck
}

type ActiveRelationship = {
  id: string
  caseId: string
  name: string
  stage: string
  lastMessage: string
  lastMessageTime: string
  verified: boolean
  image: string
  unreadCount: number
  counterpartId?: string
  // 小雅私信相关字段
  hasXiaoyaUnread?: boolean        // 小雅是否有未读私信
  xiaoyaConversationId?: string    // 小雅会话ID
  xiaoyaLastMessage?: string       // 小雅最新私信内容
}

type SwipeAction = {
  key: string
  label: string
  icon: typeof Pin
  tone?: 'default' | 'destructive'
  onClick: () => void
}

type SwipeableCardProps = {
  open: boolean
  onOpenChange: (next: boolean) => void
  actions: SwipeAction[]
  onMainClick?: () => void
  ariaLabel?: string
  className?: string
  style?: React.CSSProperties
  children: React.ReactNode
  isPinned?: boolean
  hasUnread?: boolean
}

function SwipeableCard({
  open,
  onOpenChange,
  actions,
  onMainClick,
  ariaLabel,
  className,
  style,
  children,
  isPinned,
  hasUnread,
}: SwipeableCardProps) {
  const actionsWidth = actions.length * 76
  const [dragOffset, setDragOffset] = useState(0)
  const gesture = useRef({
    startX: 0,
    startY: 0,
    dragging: false,
    horizontal: false,
    pointerId: -1,
  })

  useEffect(() => {
    if (!open) setDragOffset(0)
  }, [open])

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement | null
    if (target?.closest('button')) return
    gesture.current = {
      startX: event.clientX,
      startY: event.clientY,
      dragging: true,
      horizontal: false,
      pointerId: event.pointerId,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!gesture.current.dragging || gesture.current.pointerId !== event.pointerId) return
    const deltaX = event.clientX - gesture.current.startX
    const deltaY = event.clientY - gesture.current.startY
    if (!gesture.current.horizontal) {
      if (Math.abs(deltaX) < 8) return
      if (Math.abs(deltaY) > Math.abs(deltaX)) return
      gesture.current.horizontal = true
    }
    const nextOffset = open ? Math.max(0, Math.min(actionsWidth, actionsWidth - deltaX)) : Math.max(0, Math.min(actionsWidth, -deltaX))
    setDragOffset(nextOffset)
  }

  function finishGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (gesture.current.pointerId !== event.pointerId) return
    const shouldOpen = dragOffset > actionsWidth * 0.4
    const wasHorizontal = gesture.current.horizontal
    gesture.current = {
      startX: 0,
      startY: 0,
      dragging: false,
      horizontal: false,
      pointerId: -1,
    }
    setDragOffset(shouldOpen ? actionsWidth : 0)
    onOpenChange(shouldOpen)
    if (!wasHorizontal && !open && onMainClick) onMainClick()
  }

  const offset = open ? Math.max(actionsWidth, dragOffset) : dragOffset

  return (
    <div className={className} style={style} aria-label={ariaLabel}>
      <div className={`relative w-full overflow-hidden rounded-xl ${isPinned ? 'ring-2 ring-gold/40' : ''} ${hasUnread ? 'ring-2 ring-rose/40' : ''}`}>
        {/* 未读指示条 */}
        {hasUnread && (
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-rose z-20 rounded-l-xl" />
        )}
        <div className="absolute inset-y-0 right-0 flex justify-end" style={{ width: actionsWidth }}>
          {actions.map((action) => {
            const Icon = action.icon
            return (
              <button
                key={action.key}
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  action.onClick()
                  onOpenChange(false)
                  setDragOffset(0)
                }}
                className={`flex flex-1 flex-col items-center justify-center gap-1 text-xs text-white ${
                  action.tone === 'destructive' ? 'bg-destructive' : 'bg-primary'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{action.label}</span>
              </button>
            )
          })}
        </div>
        <div
          className="relative z-10 w-full bg-card transition-transform duration-200 ease-out touch-pan-y"
          style={{ transform: `translateX(${-offset}px)` }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={finishGesture}
          onPointerCancel={finishGesture}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

function buildStageTip(item: ProxyIntroCase): string {
  const name = item.counterpart_name || '对方'
  const stage = item.stage_label || '牵线中'
  if (item.main_conversation_id) return `你和${name}已经进入聊天`
  if (item.case_status === 'awaiting_reply') {
    if (item.role === 'requester') {
      return '已把您推荐给对方，等他回复'
    }
    return `已把${name}推荐给对方，等她回复`
  }
  if (item.case_status === 'accepted') return `${name}也愿意认识，可以开始聊天了`
  if (item.case_status === 'declined') return `${name}这次先不考虑`
  if (item.case_status === 'timed_out') return `${name}暂时没有回复`
  return `${name}当前状态：${stage}`
}

export default function RelationshipsPage({ onOpenChat, onStartVerification, onNavigateToDiscover, onViewCandidate }: RelationshipsPageProps) {
  const [cases, setCases] = useState<ProxyIntroCase[]>([])
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([])
  const [pinnedCardIds, setPinnedCardIds] = useState<Record<string, boolean>>({})
  const [readCardIds, setReadCardIds] = useState<Record<string, boolean>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [emptyHint, setEmptyHint] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)
  const [isPulling, setIsPulling] = useState(false)
  const touchStartY = useRef(0)
  const [actingCaseId, setActingCaseId] = useState<string | null>(null)
  const [unreadByCaseId, setUnreadByCaseId] = useState<Record<string, number>>({})
  const [lastMessagesByCaseId, setLastMessagesByCaseId] = useState<Record<string, { content: string; time: string }>>({})
  const [openCardId, setOpenCardId] = useState<string | null>(null)
  const [stageTipText, setStageTipText] = useState<string | null>(null)
  const [showStageTipForCase, setShowStageTipForCase] = useState<string | null>(null)
  const [deleteConfirmCaseId, setDeleteConfirmCaseId] = useState<string | null>(null)
  const { usingMockData, applyProvenance } = usePageDataSource()

  // 小雅私信状态
  const [xiaoyaUnreadByCaseId, setXiaoyaUnreadByCaseId] = useState<Record<string, {
    hasUnread: boolean
    conversationId: string
    lastMessage: string
  }>>({})
  const [openXiaoyaCaseId, setOpenXiaoyaCaseId] = useState<string | null>(null) // 当前展开的复盘面板

  // 加载数据的核心函数
  const loadCases = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
    }
    setLoadError(null)
    setEmptyHint(null)
    try {
      const userId = getUserId()
      const profileId = getProfileId()
      const [caseData, trustHub] = await Promise.all([
        fetchMyProxyIntroCases(),
        userId ? fetchTrustHub({ userId, profileId }).catch(() => null) : Promise.resolve(null),
      ])
      const nextCases = caseData.cases || []
      setCases(nextCases)

      // 获取活跃对话的最新消息（限制并发数量）
      const activeCaseIds = nextCases
        .filter((item) => item.main_conversation_id && item.case_id)
        .map((item) => String(item.case_id))
        .slice(0, 10) // 限制最多10个并发请求

      if (activeCaseIds.length > 0 && userId) {
        const timelines = await Promise.allSettled(
          activeCaseIds.map(async (caseId) => ({
            caseId,
            data: await fetchCaseConversationTimeline(caseId, userId).catch(() => null),
          })),
        )
        const lastMessages: Record<string, { content: string; time: string }> = {}
        // 小雅私信状态
        const xiaoyaUnreadByCaseId: Record<string, {
          hasUnread: boolean
          conversationId: string
          lastMessage: string
        }> = {}

        timelines.forEach((result) => {
          if (result.status === 'fulfilled' && result.value.data?.conversations) {
            const item = result.value
            const data = item.data
            if (!data) return

            // 找到 main_group 对话的最新消息
            const mainConv = data.conversations.find(
              (c) => c.conversation.channel_key === 'main_group',
            )
            if (mainConv?.messages && mainConv.messages.length > 0) {
              const lastMsg = mainConv.messages[mainConv.messages.length - 1]
              lastMessages[item.caseId] = {
                content: lastMsg.body || '',
                time: lastMsg.created_at || '',
              }
            }

            // ✅ 检测 assistant_dm 会话（小雅私信，channel_key 为 assistant_dm_a 或 assistant_dm_b）
            const assistantDm = data.conversations.find(
              (c) => c.conversation.channel_key.startsWith('assistant_dm'),
            )
            if (assistantDm && assistantDm.messages && assistantDm.messages.length > 0) {
              // 检查会话成员中是否有 agent 角色
              const agentMember = assistantDm.conversation.members?.find(
                (m) => m.member_role === 'agent',
              )
              const lastDmMsg = assistantDm.messages[assistantDm.messages.length - 1]

              // 如果消息作者是 agent，则是小雅私信
              if (agentMember && lastDmMsg.author_id === agentMember.participant_id) {
                xiaoyaUnreadByCaseId[item.caseId] = {
                  hasUnread: true,
                  conversationId: assistantDm.conversation.conversation_id,
                  lastMessage: lastDmMsg.body,
                }
              }
            }
          }
        })
        setLastMessagesByCaseId(lastMessages)
        setXiaoyaUnreadByCaseId(xiaoyaUnreadByCaseId)
      }

      const unreadSummary = await fetchRelationshipsUnreadSummary().catch(() => null)
      setUnreadByCaseId(unreadSummary?.byCaseId || {})
      const trustPending = mapTrustHubPendingActions(
        trustHub?.trust_hub?.verification_center?.items,
      ).map((item) => ({
        id: item.id,
        type: 'verification' as const,
        title: item.title,
        description: item.description,
        icon: BadgeCheck,
      }))
      setPendingActions(trustPending)
      if (nextCases.length === 0) {
        setEmptyHint('暂时还没有进行中的牵线记录')
      }
      const provenance = applyProvenance(false, nextCases.length > 0, '/v1/proxy-intro/cases/mine', 'proxy_intro')
      logDataProvenance('relationships', provenance)
    } catch (error) {
      const message = getErrorMessage(error, '关系页加载失败')
      setLoadError(message)
      if (canUseMockFallback()) {
        applyProvenance(true, false, '/v1/proxy-intro/cases/mine')
      }
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [applyProvenance])

  useEffect(() => {
    let cancelled = false

    async function load() {
      if (cancelled) return
      await loadCases()
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [loadCases])

  async function handleReply(caseId: string, replyType: 'accepted' | 'declined') {
    if (actingCaseId) return
    setActingCaseId(caseId)
    try {
      const response = await replyProxyIntroCase({
        caseId,
        replyType,
        source: 'relationships_page',
      })
      if (!response.case) return
      setCases((prev) => prev.map((item) => (item.case_id === caseId ? response.case! : item)))
    } catch (error) {
      setLoadError(getErrorMessage(error, replyType === 'accepted' ? '接受失败' : '暂不考虑失败'))
    } finally {
      setActingCaseId(null)
    }
  }

  async function handleOpenChat(caseId: string) {
    if (actingCaseId) return
    setActingCaseId(caseId)
    try {
      // 先获取当前 case 的用户信息
      const currentCase = cases.find((item) => String(item.case_id) === caseId)
      const userInfo: ChatUserInfo | undefined = currentCase ? {
        title: currentCase.counterpart_name || undefined,
        avatar: resolveProfileImageUrl(currentCase.counterpart_image ?? undefined, PLACEHOLDER_AVATAR),
        caseId: String(currentCase.case_id),
        counterpartId: currentCase.counterpart_profile_id ? String(currentCase.counterpart_profile_id) : undefined,
      } : undefined

      const response = await openProxyIntroChat({
        caseId,
        source: 'relationships_page',
      })
      const conversationId = String(response.conversation?.conversation_id || '').trim()
      if (!conversationId) {
        throw new Error('conversation_missing')
      }
      if (response.case) {
        setCases((prev) => prev.map((item) => (item.case_id === caseId ? response.case! : item)))
      }
      patchSessionContext({ caseId })
      onOpenChat(conversationId, userInfo)
    } catch (error) {
      setLoadError(getErrorMessage(error, '开始聊天失败'))
    } finally {
      setActingCaseId(null)
    }
  }

  function togglePinned(cardId: string) {
    setPinnedCardIds((prev) => ({ ...prev, [cardId]: !prev[cardId] }))
  }

  function markAsRead(cardId: string) {
    setReadCardIds((prev) => ({ ...prev, [cardId]: true }))
  }

  function deleteCard(cardId: string) {
    // 显示删除确认
    setDeleteConfirmCaseId(cardId)
  }

  function confirmDelete(cardId: string) {
    setCases((prev) => prev.filter((item) => String(item.case_id) !== cardId))
    setOpenCardId((prev) => (prev === cardId ? null : prev))
    setDeleteConfirmCaseId(null)
  }

  function cancelDelete() {
    setDeleteConfirmCaseId(null)
  }

  // 格式化相对时间
  function formatRelativeTime(timeStr: string): string {
    if (!timeStr) return '刚刚'
    try {
      const date = new Date(timeStr)
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffMins = Math.floor(diffMs / 60000)
      const diffHours = Math.floor(diffMs / 3600000)
      const diffDays = Math.floor(diffMs / 86400000)
      
      if (diffMins < 1) return '刚刚'
      if (diffMins < 60) return `${diffMins}分钟前`
      if (diffHours < 24) return `${diffHours}小时前`
      if (diffDays < 7) return `${diffDays}天前`
      return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
    } catch {
      return timeStr
    }
  }

  // 计算等待天数
  function getWaitingDays(item: ProxyIntroCase): number | null {
    if (item.case_status !== 'awaiting_reply') return null
    const updatedAt = item.updated_at || item.created_at
    if (!updatedAt) return null
    try {
      const date = new Date(updatedAt)
      const now = new Date()
      return Math.floor((now.getTime() - date.getTime()) / 86400000)
    } catch {
      return null
    }
  }

  if (isLoading) {
    return <RelationshipsPageSkeleton />
  }

  const pendingIntroItems = cases.filter((item) => {
    // 排除掉作为被请求方且等待回复的 case（这些显示在推荐来信中）
    if (item.role === 'candidate' && item.case_status === 'awaiting_reply') {
      return false
    }
    return !item.main_conversation_id
  })
  const activeRelationships: ActiveRelationship[] = cases
    .filter((item) => item.main_conversation_id)
    .map((item) => {
      const caseIdStr = String(item.case_id)
      const lastMsgData = lastMessagesByCaseId[caseIdStr]
      const xiaoyaData = xiaoyaUnreadByCaseId[caseIdStr]
      return {
        id: String(item.main_conversation_id),
        caseId: caseIdStr,
        name: item.counterpart_name || '对方',
        stage: item.stage_label || '已开聊',
        lastMessage: lastMsgData?.content || '开始聊天吧',
        lastMessageTime: lastMsgData?.time || item.updated_at || item.created_at || '刚刚',
        verified: true,
        image: resolveProfileImageUrl(item.counterpart_image ?? undefined, PLACEHOLDER_AVATAR),
        unreadCount: unreadByCaseId[caseIdStr] || 0,
        counterpartId: item.counterpart_profile_id ? String(item.counterpart_profile_id) : undefined,
        // 小雅私信相关字段
        hasXiaoyaUnread: xiaoyaData?.hasUnread || false,
        xiaoyaConversationId: xiaoyaData?.conversationId,
        xiaoyaLastMessage: xiaoyaData?.lastMessage,
      }
    })
    .sort((a, b) => {
      const pinDiff = Number(Boolean(pinnedCardIds[b.caseId])) - Number(Boolean(pinnedCardIds[a.caseId]))
      if (pinDiff !== 0) return pinDiff
      const unreadDiff = Number(b.unreadCount > 0) - Number(a.unreadCount > 0)
      if (unreadDiff !== 0) return unreadDiff
      return String(b.lastMessageTime).localeCompare(String(a.lastMessageTime))
    })
  if (loadError && !canUseMockFallback() && activeRelationships.length === 0 && cases.length === 0) {
    return (
      <ErrorState
        message={loadError}
        onRetry={() => window.location.reload()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {usingMockData && <DemoDataBanner />}

      {/* 删除确认弹窗 */}
      {deleteConfirmCaseId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-fade-in">
          <div className="mx-4 w-full max-w-sm rounded-2xl bg-card p-5 shadow-xl animate-scale-in">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-destructive/10 flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-destructive" />
              </div>
              <h3 className="text-base font-medium">确认删除</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-5">
              删除后将清空与对方的聊天数据，此操作无法撤销。
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={cancelDelete}
                className="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-medium"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => confirmDelete(deleteConfirmCaseId)}
                className="flex-1 rounded-lg bg-destructive px-4 py-2.5 text-sm font-medium text-destructive-foreground"
              >
                删除并清空
              </button>
            </div>
          </div>
        </div>
      )}

      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="text-lg font-medium">关系</h1>
          <p className="text-xs text-muted-foreground">管理你的缘分进度</p>
        </div>
      </header>

      {/* 待处理事项置顶显示 */}
      {pendingActions.length > 0 && (
        <div className="px-4 pt-3">
          <div className="bg-gold/10 border border-gold/30 rounded-xl p-3">
            <div className="flex items-center gap-2 mb-2">
              <BadgeCheck className="w-4 h-4 text-gold" />
              <span className="text-sm font-medium text-gold">待处理事项</span>
              <span className="ml-auto text-xs text-gold/70">{pendingActions.length}项</span>
            </div>
            {pendingActions.slice(0, 2).map((action) => (
              <button
                key={action.id}
                onClick={onStartVerification}
                className="w-full flex items-center gap-2 py-2 text-left hover:bg-gold/5 rounded-lg transition-colors"
              >
                <span className="text-sm">{action.title}</span>
                <ChevronRight className="w-4 h-4 text-muted-foreground ml-auto" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 下拉刷新指示器 */}
      <div
        className="flex items-center justify-center py-2 text-muted-foreground transition-all"
        style={{
          height: isRefreshing ? 40 : pullDistance,
          opacity: pullDistance > 0 || isRefreshing ? 1 : 0,
        }}
      >
        {isRefreshing ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : pullDistance > 60 ? (
          <span className="text-xs">释放刷新</span>
        ) : pullDistance > 0 ? (
          <span className="text-xs">下拉刷新</span>
        ) : null}
      </div>

      <div
        className="flex-1 overflow-y-auto px-4 py-4 space-y-5 pb-20"
        onTouchStart={(e) => {
          const scrollEl = e.currentTarget
          if (scrollEl.scrollTop <= 0) {
            touchStartY.current = e.touches[0].clientY
            setIsPulling(true)
          }
        }}
        onTouchMove={(e) => {
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
        }}
        onTouchEnd={() => {
          if (pullDistance > 60 && !isRefreshing) {
            void loadCases(true)
          }
          setPullDistance(0)
          setIsPulling(false)
          touchStartY.current = 0
        }}
      >
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium">正在进行中</h2>
            <span className="text-xs text-muted-foreground">{activeRelationships.length}位</span>
          </div>
          <div className="space-y-3">
            {activeRelationships.map((rel, index) => (
              <SwipeableCard
                key={rel.id}
                open={openCardId === rel.caseId}
                onOpenChange={(next) => setOpenCardId(next ? rel.caseId : null)}
                isPinned={pinnedCardIds[rel.caseId]}
                hasUnread={rel.unreadCount > 0 && !readCardIds[rel.caseId]}
                actions={[
                  {
                    key: 'pin',
                    label: pinnedCardIds[rel.caseId] ? '取消置顶' : '置顶',
                    icon: Pin,
                    onClick: () => togglePinned(rel.caseId),
                  },
                  {
                    key: 'read',
                    label: '标记已读',
                    icon: MailOpen,
                    onClick: () => markAsRead(rel.caseId),
                  },
                  {
                    key: 'delete',
                    label: '删除',
                    icon: Trash2,
                    tone: 'destructive',
                    onClick: () => deleteCard(rel.caseId),
                  },
                ]}
                onMainClick={() => onOpenChat(rel.id, { title: rel.name, avatar: rel.image, caseId: rel.caseId, counterpartId: rel.counterpartId })}
                ariaLabel={`查看与${rel.name}的对话`}
                style={{ animationDelay: `${index * 50}ms` }}
                className={`bg-card border rounded-xl hover:border-primary/30 hover:shadow-sm transition-all focus-ring animate-fade-in-up ${
                  rel.unreadCount > 0 && !readCardIds[rel.caseId] ? 'bg-rose-soft/30 border-rose/20' : 'border-border'
                }`}
              >
                <div className="p-3 pl-4">
                  <div className="flex items-center gap-3">
                    <div className="relative w-12 h-12 rounded-full overflow-hidden">
                      <Image src={rel.image} alt={rel.name} fill className="object-cover" />
                      {rel.unreadCount > 0 ? (
                        <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center shadow-sm">
                          {rel.unreadCount > 99 ? '99+' : rel.unreadCount}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{rel.name}</span>
                        {rel.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
                        {pinnedCardIds[rel.caseId] ? <span className="px-2 py-0.5 bg-gold/20 text-[10px] text-gold font-medium rounded-full">置顶</span> : null}
                        {readCardIds[rel.caseId] ? <span className="px-2 py-0.5 bg-secondary text-[10px] rounded-full">已读</span> : null}
                        <span className="ml-auto px-2 py-0.5 bg-secondary text-[10px] rounded-full">{rel.stage}</span>
                      </div>
                      <p className="text-sm text-muted-foreground truncate mt-0.5">
                        {rel.lastMessage}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-muted-foreground">{formatRelativeTime(rel.lastMessageTime)}</span>
                        {/* 小雅复盘入口 */}
                        {rel.hasXiaoyaUnread && rel.xiaoyaConversationId && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setOpenXiaoyaCaseId(openXiaoyaCaseId === rel.caseId ? null : rel.caseId)
                            }}
                            className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-100/80 text-purple-600 text-[10px] hover:bg-purple-100 transition-colors"
                          >
                            <Image
                              src="/xiaoya-avatar.png"
                              alt="小雅"
                              width={12}
                              height={12}
                              className="rounded-full"
                            />
                            <span>小雅复盘</span>
                            <span className="w-1.5 h-1.5 rounded-full bg-rose animate-pulse" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 小雅复盘面板 */}
                  {openXiaoyaCaseId === rel.caseId && rel.xiaoyaConversationId && (
                    <div className="px-3 pb-3 animate-fade-in">
                      <div className="bg-gradient-to-r from-purple-50/50 to-blue-50/50 rounded-xl p-3 border border-purple-100/50">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Image
                              src="/xiaoya-avatar.png"
                              alt="小雅"
                              width={20}
                              height={20}
                              className="rounded-full"
                            />
                            <span className="text-sm font-medium text-purple-700">小雅 · 复盘助手</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => setOpenXiaoyaCaseId(null)}
                            className="w-6 h-6 rounded-full hover:bg-purple-100 flex items-center justify-center"
                          >
                            <X className="w-4 h-4 text-purple-600" />
                          </button>
                        </div>
                        <p className="text-xs text-purple-600/80 mb-2">
                          {rel.xiaoyaLastMessage || '刚才聊得怎么样呀？有需要我帮忙跟进的吗？'}
                        </p>
                        <p className="text-[10px] text-purple-400/60">点击进入聊天页与小雅私聊更多～</p>
                      </div>
                    </div>
                  )}
                </div>
              </SwipeableCard>
            ))}
            {activeRelationships.length === 0 && (
              <EmptyRelationships
                onDiscover={onNavigateToDiscover}
                description={emptyHint || undefined}
              />
            )}
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium">牵线中</h2>
            <span className="text-xs text-muted-foreground">{pendingIntroItems.length}条</span>
          </div>
          <div className="space-y-3">
            {pendingIntroItems.map((item, index) => {
              const waitingDays = getWaitingDays(item)
              const stageLabel = waitingDays !== null && waitingDays > 0
                ? `${item.stage_label}（${waitingDays}天）`
                : item.stage_label
              return (
              <SwipeableCard
                key={`pending-${item.case_id}`}
                open={openCardId === String(item.case_id)}
                onOpenChange={(next) => setOpenCardId(next ? String(item.case_id) : null)}
                isPinned={pinnedCardIds[String(item.case_id)]}
                onMainClick={() => {
                  if (onViewCandidate && item.counterpart_profile_id) {
                    const candidate: CandidatePreview = {
                      id: String(item.counterpart_profile_id),
                      name: item.counterpart_name || '对方',
                      image: resolveProfileImageUrl(item.counterpart_image ?? undefined, PLACEHOLDER_AVATAR),
                      caseId: String(item.case_id),
                      // 牵线中的候选人使用 matched 类型，隐藏操作按钮
                      viewType: 'matched',
                      age: item.counterpart_profile?.age as number | undefined,
                      city: item.counterpart_profile?.city as string | undefined,
                      occupation: item.counterpart_profile?.job as string | undefined,
                      education: item.counterpart_profile?.education as string | undefined,
                    }
                    onViewCandidate(String(item.counterpart_profile_id), candidate)
                  }
                }}
                actions={[
                  {
                    key: 'pin',
                    label: pinnedCardIds[String(item.case_id)] ? '取消置顶' : '置顶',
                    icon: Pin,
                    onClick: () => togglePinned(String(item.case_id)),
                  },
                  {
                    key: 'read',
                    label: '标记已读',
                    icon: MailOpen,
                    onClick: () => markAsRead(String(item.case_id)),
                  },
                  {
                    key: 'delete',
                    label: '删除',
                    icon: Trash2,
                    tone: 'destructive',
                    onClick: () => deleteCard(String(item.case_id)),
                  },
                ]}
                style={{ animationDelay: `${index * 50}ms` }}
                className="bg-card border border-border rounded-xl animate-fade-in-up"
              >
                <div className="p-3">
                  <div className="flex items-center gap-3">
                    <div className="relative w-12 h-12 rounded-full overflow-hidden">
                      <Image
                        src={resolveProfileImageUrl(item.counterpart_image ?? undefined, PLACEHOLDER_AVATAR)}
                        alt={item.counterpart_name || '对方'}
                        fill
                        className="object-cover"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{item.counterpart_name || '对方'}</span>
                        <span className="text-xs text-muted-foreground">
                          {String(item.counterpart_profile?.age || '')}
                          {item.counterpart_profile?.age ? '岁' : ''}
                          {item.counterpart_profile?.city ? ` · ${String(item.counterpart_profile.city)}` : ''}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground mt-0.5 truncate">
                        {String(item.counterpart_profile?.job || item.counterpart_profile?.education || '资料待补充')}
                      </p>
                    </div>
                    <div className="relative shrink-0">
                    <button
                      type="button"
                      onClick={() => {
                        if (showStageTipForCase === String(item.case_id)) {
                          setShowStageTipForCase(null)
                          setStageTipText(null)
                        } else {
                          setStageTipText(buildStageTip(item))
                          setShowStageTipForCase(String(item.case_id))
                        }
                      }}
                      className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground cursor-pointer hover:bg-secondary/80 transition-colors"
                    >
                      {stageLabel}
                    </button>
                    {showStageTipForCase === String(item.case_id) && stageTipText && (
                      <div className="absolute top-full right-0 mt-1 px-2 py-1 rounded bg-secondary/90 text-[10px] text-muted-foreground whitespace-nowrap z-10 shadow-sm animate-fade-in">
                        {stageTipText}
                      </div>
                    )}
                  </div>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                    {pinnedCardIds[String(item.case_id)] ? <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold font-medium">置顶</span> : null}
                    {readCardIds[String(item.case_id)] ? <span className="px-2 py-0.5 rounded-full bg-secondary">已读</span> : null}
                  </div>
                  {item.can_reply ? (
                    <div className="mt-3 flex gap-2">
                      <button
                        type="button"
                        onClick={() => void handleReply(String(item.case_id), 'declined')}
                        disabled={actingCaseId === item.case_id}
                        className="flex-1 rounded-lg border border-border px-3 py-2 text-sm"
                      >
                        暂不考虑
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleReply(String(item.case_id), 'accepted')}
                        disabled={actingCaseId === item.case_id}
                        className="flex-1 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                      >
                        愿意认识
                      </button>
                    </div>
                  ) : item.can_open_chat ? (
                    <button
                      type="button"
                      onClick={() => void handleOpenChat(String(item.case_id))}
                      disabled={actingCaseId === item.case_id}
                      className="mt-3 w-full rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                    >
                      {actingCaseId === item.case_id ? '处理中' : '开始聊天'}
                    </button>
                  ) : null}
                </div>
              </SwipeableCard>
              )
            })}
            {pendingIntroItems.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">
                暂无进行中的牵线记录
              </div>
            ) : null}
          </div>
        </section>

              </div>
    </div>
  )
}
