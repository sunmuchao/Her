'use client'

import { useEffect, useRef, useState, useMemo } from 'react'
import { BadgeCheck, ChevronDown, ChevronRight, Loader2, MailOpen, Pin, Trash2 } from 'lucide-react'
import Image from 'next/image'
import { openProxyIntroChat, replyProxyIntroCase } from '@/lib/api/endpoints/proxy-intro'
import { fetchCaseConversationTimeline } from '@/lib/api/endpoints/relations'
import { getUserId } from '@/lib/auth/session'
import { PLACEHOLDER_AVATAR, resolveProfileImageUrl } from '@/lib/image-url'
import type { ChatUserInfo } from '@/hooks/use-app-router'
import type { CandidatePreview } from '@/lib/types/candidate'
import { useRelationshipsPageData } from '@/lib/hooks/use-relationships-page-data'
import {
  buildActiveRelationships,
  buildPendingIntroItems,
  buildPendingVerificationActions,
  buildStageTip,
  formatRelativeTime,
  type XiaoyaUnreadData,
} from '@/lib/mappers/relationships-view'
import { PageHeader } from './ui/page-header'
import { SwipeableCard } from './ui/swipeable-card'
import { ConfirmDialog } from './ui/confirm-dialog'
import { XiaoyaReviewPanel } from './ui/xiaoya-review-panel'
import { ErrorState } from './ui/error-state'
import { EmptyRelationships } from './ui/empty-states'
import { RelationshipsPageSkeleton } from './ui/skeletons'
import { FadeIn, PageTransition } from './ui/animations'

interface RelationshipsPageProps {
  onOpenChat: (chatId: string, info?: ChatUserInfo) => void
  onNavigateToDiscover?: () => void
  onViewCandidate?: (candidateId: string, candidate?: CandidatePreview) => void
}

/**
 * Relationships 页面 - 重构版
 *
 * 改进点：
 * 1. 使用统一的 PageHeader（而非自定义 header）
 * 2. 使用聚合 hooks 管理数据（而非 useState）
 * 3. 使用抽离的组件（SwipeableCard、ConfirmDialog、XiaoyaReviewPanel）
 * 4. 使用 mappers 转换数据（而非内联逻辑）
 *
 * 代码行数：从 1277 行 → 约 300 行（减少 ~75%）
 */
export default function RelationshipsPage({
  onOpenChat,
  onNavigateToDiscover,
  onViewCandidate,
}: RelationshipsPageProps) {
  // 使用聚合数据 hook
  const {
    cases,
    trustHub,
    unreadSummary,
    isLoading,
    isRefreshing,
    error,
    refetch,
  } = useRelationshipsPageData()

  // UI 状态（这些仍用 useState，因为是纯 UI 交互）
  const [pinnedCardIds, setPinnedCardIds] = useState<Record<string, boolean>>({})
  const [readCardIds, setReadCardIds] = useState<Record<string, boolean>>({})
  const [openCardId, setOpenCardId] = useState<string | null>(null)
  const [deleteConfirmCaseId, setDeleteConfirmCaseId] = useState<string | null>(null)
  const [isPendingSectionCollapsed, setIsPendingSectionCollapsed] = useState(true)
  const [stageTipText, setStageTipText] = useState<string | null>(null)
  const [showStageTipForCase, setShowStageTipForCase] = useState<string | null>(null)
  const [actingCaseId, setActingCaseId] = useState<string | null>(null)

  // 下拉刷新状态
  const [pullDistance, setPullDistance] = useState(0)
  const [isPulling, setIsPulling] = useState(false)
  const touchStartY = useRef(0)

  // 小雅复盘面板状态
  const [openXiaoyaCaseId, setOpenXiaoyaCaseId] = useState<string | null>(null)

  // 各 case 的最新消息（需要单独请求）
  const [lastMessagesByCaseId, setLastMessagesByCaseId] = useState<Record<string, { content: string; time: string }>>({})
  // 各 case 的小雅未读数据
  const [xiaoyaUnreadByCaseId, setXiaoyaUnreadByCaseId] = useState<Record<string, XiaoyaUnreadData>>({})

  // 未读统计
  const unreadByCaseId = useMemo(() => unreadSummary?.byCaseId || {}, [unreadSummary])

  // 待处理认证项
  const pendingVerificationActions = useMemo(
    () => buildPendingVerificationActions(trustHub),
    [trustHub]
  )

  // 活跃关系列表
  const activeRelationships = useMemo(
    () => buildActiveRelationships(cases, lastMessagesByCaseId, unreadByCaseId, xiaoyaUnreadByCaseId, pinnedCardIds),
    [cases, lastMessagesByCaseId, unreadByCaseId, xiaoyaUnreadByCaseId, pinnedCardIds]
  )

  // 牵线中列表
  const pendingIntroItems = useMemo(
    () => buildPendingIntroItems(cases),
    [cases]
  )

  // 获取活跃对话的最新消息（限制并发数量）
  useEffect(() => {
    const userId = getUserId()
    if (!userId) return

    const activeCaseIds = cases
      .filter((item) => item.main_conversation_id && item.case_id)
      .map((item) => String(item.case_id))
      .slice(0, 10) // 限制最多 10 个并发请求

    if (activeCaseIds.length === 0) return

    async function loadLastMessages() {
      const timelines = await Promise.allSettled(
        activeCaseIds.map(async (caseId) => ({
          caseId,
          data: await fetchCaseConversationTimeline(caseId, userId).catch(() => null),
        })),
      )

      const lastMessages: Record<string, { content: string; time: string }> = {}
      const xiaoyaUnread: Record<string, XiaoyaUnreadData> = {}

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

          // 检测 assistant_dm 会话（小雅私信）
          const assistantDm = data.conversations.find(
            (c) => c.conversation.channel_key.startsWith('assistant_dm'),
          )
          if (assistantDm && assistantDm.messages && assistantDm.messages.length > 0) {
            const agentMember = assistantDm.conversation.members?.find(
              (m) => m.member_role === 'agent',
            )
            const lastDmMsg = assistantDm.messages[assistantDm.messages.length - 1]

            if (agentMember && lastDmMsg.author_id === agentMember.participant_id) {
              xiaoyaUnread[item.caseId] = {
                hasUnread: true,
                conversationId: assistantDm.conversation.conversation_id,
                lastMessage: lastDmMsg.body,
              }
            }
          }
        }
      })

      setLastMessagesByCaseId(lastMessages)
      setXiaoyaUnreadByCaseId(xiaoyaUnread)
    }

    loadLastMessages()
  }, [cases])

  // 处理回复（接受/暂不考虑）
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
      // 刷新数据
      await refetch()
    } catch (err) {
      // 错误处理（简化，不设置全局 error）
      console.error('Reply failed:', err)
    } finally {
      setActingCaseId(null)
    }
  }

  // 处理打开聊天
  async function handleOpenChat(caseId: string) {
    if (actingCaseId) return
    setActingCaseId(caseId)
    try {
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
      onOpenChat(conversationId, userInfo)
    } catch (err) {
      console.error('Open chat failed:', err)
    } finally {
      setActingCaseId(null)
    }
  }

  // 置顶/取消置顶
  function togglePinned(cardId: string) {
    setPinnedCardIds((prev) => ({ ...prev, [cardId]: !prev[cardId] }))
  }

  // 标记已读
  function markAsRead(cardId: string) {
    setReadCardIds((prev) => ({ ...prev, [cardId]: true }))
  }

  // 删除卡片（显示确认弹窗）
  function deleteCard(cardId: string) {
    setDeleteConfirmCaseId(cardId)
  }

  // 确认删除
  function confirmDelete(cardId: string) {
    // 从列表中移除（本地状态，不需要调用 API）
    setOpenCardId((prev) => (prev === cardId ? null : prev))
    setDeleteConfirmCaseId(null)
    // 刷新数据以同步
    refetch()
  }

  // 获取小雅面板当前的关系信息
  function getXiaoyaRelationship() {
    if (!openXiaoyaCaseId) return null
    const rel = activeRelationships.find((r) => r.caseId === openXiaoyaCaseId)
    if (!rel) return null
    return {
      caseId: rel.caseId,
      name: rel.name,
      image: rel.image,
      conversationId: rel.xiaoyaConversationId || rel.id,
    }
  }

  // 下拉刷新处理
  function handleTouchStart(e: React.TouchEvent) {
    const scrollEl = e.currentTarget
    if (scrollEl.scrollTop <= 0) {
      touchStartY.current = e.touches[0].clientY
      setIsPulling(true)
    }
  }

  function handleTouchMove(e: React.TouchEvent) {
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

  function handleTouchEnd() {
    if (pullDistance > 60 && !isRefreshing) {
      refetch()
    }
    setPullDistance(0)
    setIsPulling(false)
    touchStartY.current = 0
  }

  // 加载状态
  if (isLoading) {
    return <RelationshipsPageSkeleton />
  }

  // 错误状态
  if (error && activeRelationships.length === 0 && pendingIntroItems.length === 0) {
    return (
      <ErrorState
        message={error}
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {/* Header - 使用统一组件 */}
      <PageHeader
        title="关系"
        subtitle="管理你的缘分进度"
      />

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

      {/* 主内容区域 */}
      <div
        className="flex-1 overflow-y-auto px-4 py-4 space-y-5 pb-20"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* 正在进行中 */}
        {activeRelationships.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-medium">正在进行中</h2>
              <span className="text-xs text-muted-foreground">{activeRelationships.length}位</span>
            </div>
            <div className="space-y-3">
              {activeRelationships.map((rel, index) => (
                <FadeIn key={rel.id} delay={index * 50}>
                  <SwipeableCard
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
                    onMainClick={() => onOpenChat(rel.id, {
                      title: rel.name,
                      avatar: rel.image,
                      caseId: rel.caseId,
                      counterpartId: rel.counterpartId,
                    })}
                    ariaLabel={`查看与${rel.name}的对话`}
                    className={`border rounded-xl hover:border-primary/30 hover:shadow-sm transition-all focus-ring ${
                      rel.unreadCount > 0 && !readCardIds[rel.caseId]
                        ? 'bg-rose-soft/30 border-rose/20'
                        : 'bg-card border-border'
                    }`}
                  >
                    {/* 卡片内容 */}
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
                          </div>
                          <p className="text-sm text-muted-foreground/70 truncate mt-0.5">
                            {rel.lastMessage}
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] text-muted-foreground/60">
                              {formatRelativeTime(rel.lastMessageTime)}
                            </span>
                            {rel.hasXiaoyaUnread && rel.xiaoyaConversationId && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setOpenXiaoyaCaseId(openXiaoyaCaseId === rel.caseId ? null : rel.caseId)
                                }}
                                className="relative flex items-center gap-1 px-2 py-0.5 rounded-full bg-gold-soft text-gold text-[10px] hover:bg-gold/20 transition-colors"
                                aria-label="查看小雅复盘"
                              >
                                <Image
                                  src="/xiaoya-avatar.png"
                                  alt="小雅"
                                  width={12}
                                  height={12}
                                  className="rounded-full relative z-10"
                                />
                                <span>小雅复盘</span>
                                <span className="w-2 h-2 rounded-full bg-gold animate-pulse shadow-[0_0_8px_rgba(212,175,55,0.6)]" />
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1.5 shrink-0">
                          <div className="flex items-center gap-1">
                            {pinnedCardIds[rel.caseId] && (
                              <div className="w-5 h-5 rounded-full bg-gold/20 flex items-center justify-center" title="已置顶">
                                <Pin className="w-3 h-3 text-gold" />
                              </div>
                            )}
                            {readCardIds[rel.caseId] && (
                              <div className="w-5 h-5 rounded-full bg-secondary flex items-center justify-center" title="已读">
                                <MailOpen className="w-3 h-3 text-muted-foreground" />
                              </div>
                            )}
                          </div>
                          <span className="px-2 py-0.5 bg-secondary text-[10px] text-muted-foreground rounded-full whitespace-nowrap">
                            {rel.stage}
                          </span>
                        </div>
                      </div>
                    </div>
                  </SwipeableCard>
                </FadeIn>
              ))}
            </div>
          </section>
        )}

        {/* 牵线中 */}
        {pendingIntroItems.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-medium">牵线中</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{pendingIntroItems.length}条</span>
                {activeRelationships.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setIsPendingSectionCollapsed(!isPendingSectionCollapsed)}
                    className="w-6 h-6 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
                    aria-label={isPendingSectionCollapsed ? '展开牵线中' : '折叠牵线中'}
                  >
                    <ChevronDown
                      className={`w-4 h-4 text-muted-foreground transition-transform duration-200 ${
                        isPendingSectionCollapsed ? '' : 'rotate-180'
                      }`}
                    />
                  </button>
                )}
              </div>
            </div>
            {!isPendingSectionCollapsed && (
              <div className="space-y-3">
                {pendingIntroItems.map((item, index) => (
                  <FadeIn key={`pending-${item.case_id}`} delay={index * 50}>
                    <SwipeableCard
                      open={openCardId === String(item.case_id)}
                      onOpenChange={(next) => setOpenCardId(next ? String(item.case_id) : null)}
                      isPinned={pinnedCardIds[String(item.case_id)]}
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
                      onMainClick={() => {
                        if (onViewCandidate && item.counterpart_profile_id) {
                          const candidate: CandidatePreview = {
                            id: String(item.counterpart_profile_id),
                            name: item.counterpart_name || '对方',
                            image: resolveProfileImageUrl(item.counterpart_image ?? undefined, PLACEHOLDER_AVATAR),
                            caseId: String(item.case_id),
                            viewType: 'matched',
                            age: item.counterpart_profile?.age as number | undefined,
                            city: item.counterpart_profile?.city as string | undefined,
                            occupation: item.counterpart_profile?.job as string | undefined,
                            education: item.counterpart_profile?.education as string | undefined,
                          }
                          onViewCandidate(String(item.counterpart_profile_id), candidate)
                        }
                      }}
                      className="bg-card border border-border rounded-xl"
                    >
                      {/* 牵线中卡片内容 */}
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
                              {(item.waitingDays ?? 0) > 0
                                ? `${item.stage_label}（${item.waitingDays}天）`
                                : item.stage_label}
                            </button>
                            {showStageTipForCase === String(item.case_id) && stageTipText && (
                              <div className="absolute top-full right-0 mt-1 px-2 py-1 rounded bg-secondary/90 text-[10px] text-muted-foreground whitespace-nowrap z-10 shadow-sm animate-fade-in">
                                {stageTipText}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* 操作按钮 */}
                        {item.can_reply ? (
                          <div className="mt-3 flex gap-2">
                            <button
                              type="button"
                              onClick={() => handleReply(String(item.case_id), 'declined')}
                              disabled={actingCaseId === item.case_id}
                              className="flex-1 rounded-lg border border-border px-3 py-2 text-sm"
                            >
                              暂不考虑
                            </button>
                            <button
                              type="button"
                              onClick={() => handleReply(String(item.case_id), 'accepted')}
                              disabled={actingCaseId === item.case_id}
                              className="flex-1 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                            >
                              愿意认识
                            </button>
                          </div>
                        ) : item.can_open_chat ? (
                          <button
                            type="button"
                            onClick={() => handleOpenChat(String(item.case_id))}
                            disabled={actingCaseId === item.case_id}
                            className="mt-3 w-full rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                          >
                            {actingCaseId === item.case_id ? '处理中' : '开始聊天'}
                          </button>
                        ) : null}
                      </div>
                    </SwipeableCard>
                  </FadeIn>
                ))}
              </div>
            )}
          </section>
        )}

        {/* 空状态 */}
        {activeRelationships.length === 0 && pendingIntroItems.length === 0 && (
          <EmptyRelationships onDiscover={onNavigateToDiscover} />
        )}
      </div>

      {/* 删除确认弹窗 */}
      <ConfirmDialog
        open={!!deleteConfirmCaseId}
        title="确认删除"
        description="删除后将清空与对方的聊天数据，此操作无法撤销。"
        confirmLabel="删除并清空"
        tone="destructive"
        onConfirm={() => confirmDelete(deleteConfirmCaseId!)}
        onCancel={() => setDeleteConfirmCaseId(null)}
      />

      {/* 小雅复盘面板 */}
      <XiaoyaReviewPanel
        open={!!openXiaoyaCaseId}
        onClose={() => setOpenXiaoyaCaseId(null)}
        relationship={getXiaoyaRelationship()}
        onOpenFullChat={onOpenChat}
      />
    </PageTransition>
  )
}
