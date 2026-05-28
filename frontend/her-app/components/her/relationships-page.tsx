'use client'

import { useEffect, useState } from 'react'
import { BadgeCheck, ChevronRight, Heart, MessageCircle, AlertCircle } from 'lucide-react'
import Image from 'next/image'
import { fetchRelationshipsUnreadSummary } from '@/lib/api/endpoints/chat'
import { fetchTrustHub } from '@/lib/api/endpoints/trust-hub'
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

function buildActivityText(item: ProxyIntroCase): string {
  const name = item.counterpart_name || '对方'
  const stage = item.stage_label || '牵线中'
  if (item.main_conversation_id) return `你和${name}已经进入聊天`
  if (item.case_status === 'awaiting_reply') return `已把${name}推荐给对方，等她回复`
  if (item.case_status === 'accepted') return `${name}也愿意认识，可以开始聊天了`
  if (item.case_status === 'declined') return `${name}这次先不考虑`
  if (item.case_status === 'timed_out') return `${name}暂时没有回复`
  return `${name}当前状态：${stage}`
}

export default function RelationshipsPage({ onOpenChat, onStartVerification }: RelationshipsPageProps) {
  const [cases, setCases] = useState<ProxyIntroCase[]>([])
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [emptyHint, setEmptyHint] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [actingCaseId, setActingCaseId] = useState<string | null>(null)
  const [unreadByCaseId, setUnreadByCaseId] = useState<Record<string, number>>({})
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
      console.log('[relationships] 构建活跃关系:', {
        case_id: item.case_id,
        counterpart_name: item.counterpart_name,
        counterpart_image: item.counterpart_image,
      })
      return {
        id: String(item.main_conversation_id),
        caseId: String(item.case_id),
        name: item.counterpart_name || '对方',
        stage: item.stage_label || '已开聊',
        lastMessage: item.case_status === 'closed' ? '已进入双向聊天' : '已进入聊天，继续了解吧',
        lastMessageTime: item.updated_at || item.created_at || '刚刚',
        verified: true,
        image: resolveProfileImageUrl(item.counterpart_image ?? undefined, PLACEHOLDER_AVATAR),
        unreadCount: unreadByCaseId[String(item.case_id)] || 0,
      }
    })
  const recentActivities = cases.slice(0, 5).map((item, index) => ({
    id: String(item.case_id || index),
    content: buildActivityText(item),
    time: item.updated_at || item.created_at || '刚刚',
    type: item.main_conversation_id ? 'greeting' as const : item.case_status === 'accepted' ? 'match' as const : 'view' as const,
  }))

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
              <button
                key={rel.id}
                onClick={() => {
                  console.log('[relationships] 点击活跃关系卡片:', { id: rel.id, name: rel.name, image: rel.image })
                  onOpenChat(rel.id, { title: rel.name, avatar: rel.image })
                }}
                className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 hover:shadow-sm transition-all focus-ring animate-fade-in-up"
                style={{ animationDelay: `${index * 50}ms` }}
                aria-label={`查看与${rel.name}的对话`}
              >
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
                      <span className="ml-auto px-2 py-0.5 bg-secondary text-[10px] rounded-full">{rel.stage}</span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate mt-0.5">
                      {rel.unreadCount > 0 ? `有${rel.unreadCount}条新消息` : rel.lastMessage}
                    </p>
                    <span className="text-[10px] text-muted-foreground">{rel.lastMessageTime}</span>
                  </div>
                </div>
              </button>
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
              <div
                key={`pending-${item.case_id}`}
                className="bg-card border border-border rounded-xl p-3 animate-fade-in-up"
                style={{ animationDelay: `${index * 50}ms` }}
              >
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
                    <p className="text-xs text-muted-foreground mt-1">{buildActivityText(item)}</p>
                  </div>
                  <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                    {item.stage_label}
                  </span>
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

        {recentActivities.length > 0 && (
          <section>
            <h2 className="text-sm font-medium mb-2">最近动态</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {recentActivities.map((activity, i) => (
                <div key={activity.id} className={`px-4 py-3 flex items-center gap-3 ${i !== recentActivities.length - 1 ? 'border-b border-border' : ''}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    activity.type === 'view' ? 'bg-secondary' : activity.type === 'match' ? 'bg-gold/10' : 'bg-rose/10'
                  }`}>
                    {activity.type === 'view' && <MessageCircle className="w-4 h-4 text-muted-foreground" />}
                    {activity.type === 'match' && <Heart className="w-4 h-4 text-gold" />}
                    {activity.type === 'greeting' && <Heart className="w-4 h-4 text-rose" />}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm">{activity.content}</p>
                    <span className="text-[10px] text-muted-foreground">{activity.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="bg-secondary rounded-xl p-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground leading-relaxed">
            详情页只表达意愿；真正的状态变化、对方回复、开聊入口统一放在关系页。
          </p>
        </div>
      </div>
    </div>
  )
}
