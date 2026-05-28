'use client'

import { useEffect, useRef, useState } from 'react'
import { BadgeCheck, ChevronRight, MailOpen, Pin, Trash2 } from 'lucide-react'
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
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { EmptyRelationships } from './ui/empty-states'
import { RelationshipsPageSkeleton } from './ui/skeletons'

interface RelationshipsPageProps {
  onOpenChat: (chatId: string, info?: ChatUserInfo) => void
  onStartVerification: () => void
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
      <div className="relative w-full overflow-hidden rounded-xl">
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

export default function RelationshipsPage({ onOpenChat, onStartVerification }: RelationshipsPageProps) {
  const [cases, setCases] = useState<ProxyIntroCase[]>([])
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([])
  const [pinnedCardIds, setPinnedCardIds] = useState<Record<string, boolean>>({})
  const [readCardIds, setReadCardIds] = useState<Record<string, boolean>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [emptyHint, setEmptyHint] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [actingCaseId, setActingCaseId] = useState<string | null>(null)
  const [unreadByCaseId, setUnreadByCaseId] = useState<Record<string, number>>({})
  const [lastMessagesByCaseId, setLastMessagesByCaseId] = useState<Record<string, { content: string; time: string }>>({})
  const [openCardId, setOpenCardId] = useState<string | null>(null)
  const [stageTipText, setStageTipText] = useState<string | null>(null)
  const [showStageTipForCase, setShowStageTipForCase] = useState<string | null>(null)
  const { usingMockData, applyProvenance } = usePageDataSource()

  useEffect(() => {
    let cancelled = false

    async function loadCases() {
      setIsLoading(true)
      setLoadError(null)
      setEmptyHint(null)
      try {
        const userId = getUserId()
        const profileId = getProfileId()
        const [caseData, trustHub] = await Promise.all([
          fetchMyProxyIntroCases(),
          userId ? fetchTrustHub({ userId, profileId }).catch(() => null) : Promise.resolve(null),
        ])
        if (cancelled) return
        const nextCases = caseData.cases || []
        setCases(nextCases)

        // 获取活跃对话的最新消息
        const activeCaseIds = nextCases
          .filter((item) => item.main_conversation_id && item.case_id)
          .map((item) => String(item.case_id))

        if (activeCaseIds.length > 0 && userId) {
          const timelines = await Promise.all(
            activeCaseIds.map(async (caseId) => ({
              caseId,
              data: await fetchCaseConversationTimeline(caseId, userId).catch(() => null),
            })),
          )
          if (!cancelled) {
            const lastMessages: Record<string, { content: string; time: string }> = {}
            timelines.forEach((item) => {
              if (item.data?.conversations) {
                // 找到 main_group 对话的最新消息
                const mainConv = item.data.conversations.find(
                  (c) => c.conversation.channel_key === 'main_group',
                )
                if (mainConv?.messages?.length > 0) {
                  const lastMsg = mainConv.messages[mainConv.messages.length - 1]
                  lastMessages[item.caseId] = {
                    content: lastMsg.body || '',
                    time: lastMsg.created_at || '',
                  }
                }
              }
            })
            setLastMessagesByCaseId(lastMessages)
          }
        }

        const unreadSummary = await fetchRelationshipsUnreadSummary().catch(() => null)
        if (cancelled) return
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
        if (cancelled) return
        const message = getErrorMessage(error, '关系页加载失败')
        setLoadError(message)
        if (canUseMockFallback()) {
          applyProvenance(true, false, '/v1/proxy-intro/cases/mine')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadCases()
    return () => {
      cancelled = true
    }
  }, [applyProvenance])

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
    setCases((prev) => prev.filter((item) => String(item.case_id) !== cardId))
    setOpenCardId((prev) => (prev === cardId ? null : prev))
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
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="text-lg font-medium">关系</h1>
          <p className="text-xs text-muted-foreground">双向意愿、牵线进度、开聊入口都在这里</p>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5 pb-20">
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
                onMainClick={() => onOpenChat(rel.id, { title: rel.name, avatar: rel.image })}
                ariaLabel={`查看与${rel.name}的对话`}
                style={{ animationDelay: `${index * 50}ms` }}
                className="bg-card border border-border rounded-xl hover:border-primary/30 hover:shadow-sm transition-all focus-ring animate-fade-in-up"
              >
                <div className="p-3">
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
                        {pinnedCardIds[rel.caseId] ? <span className="px-2 py-0.5 bg-gold/10 text-[10px] text-gold rounded-full">置顶</span> : null}
                        {readCardIds[rel.caseId] ? <span className="px-2 py-0.5 bg-secondary text-[10px] rounded-full">已读</span> : null}
                        <span className="ml-auto px-2 py-0.5 bg-secondary text-[10px] rounded-full">{rel.stage}</span>
                      </div>
                      <p className="text-sm text-muted-foreground truncate mt-0.5">
                        {rel.unreadCount > 0 ? `有${rel.unreadCount}条新消息` : rel.lastMessage}
                      </p>
                      <span className="text-[10px] text-muted-foreground">{rel.lastMessageTime}</span>
                    </div>
                  </div>
                </div>
              </SwipeableCard>
            ))}
            {activeRelationships.length === 0 && (
              <EmptyRelationships
                onDiscover={() => {}}
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
            {pendingIntroItems.map((item, index) => (
              <SwipeableCard
                key={`pending-${item.case_id}`}
                open={openCardId === String(item.case_id)}
                onOpenChange={(next) => setOpenCardId(next ? String(item.case_id) : null)}
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
                    <span
                      onMouseEnter={() => {
                        setStageTipText(buildStageTip(item))
                        setShowStageTipForCase(String(item.case_id))
                      }}
                      onMouseLeave={() => {
                        setShowStageTipForCase(null)
                        setStageTipText(null)
                      }}
                      onTouchStart={() => {
                        setStageTipText(buildStageTip(item))
                        setShowStageTipForCase(String(item.case_id))
                      }}
                      onTouchEnd={() => {
                        setTimeout(() => {
                          setShowStageTipForCase(null)
                          setStageTipText(null)
                        }, 1500)
                      }}
                      className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground cursor-default"
                    >
                      {item.stage_label}
                    </span>
                    {showStageTipForCase === String(item.case_id) && stageTipText && (
                      <div className="absolute top-full right-0 mt-1 px-2 py-1 rounded bg-secondary/90 text-[10px] text-muted-foreground whitespace-nowrap z-10 shadow-sm animate-fade-in">
                        {stageTipText}
                      </div>
                    )}
                  </div>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                    {pinnedCardIds[String(item.case_id)] ? <span className="px-2 py-0.5 rounded-full bg-gold/10 text-gold">置顶</span> : null}
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
            ))}
            {pendingIntroItems.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">
                暂无进行中的牵线记录
              </div>
            ) : null}
          </div>
        </section>

        {pendingActions.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">待处理</h2>
            <div className="space-y-2">
              {pendingActions.map((action) => {
                const Icon = action.icon
                return (
                  <button
                    key={action.id}
                    onClick={onStartVerification}
                    className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-secondary flex items-center justify-center">
                        <Icon className="w-4 h-4 text-muted-foreground" />
                      </div>
                      <div className="flex-1">
                        <h3 className="text-sm font-medium">{action.title}</h3>
                        <p className="text-xs text-muted-foreground">{action.description}</p>
                      </div>
                      <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    </div>
                  </button>
                )
              })}
            </div>
          </section>
        )}

              </div>
    </div>
  )
}
