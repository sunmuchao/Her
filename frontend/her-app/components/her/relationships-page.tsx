'use client'

import { useEffect, useState } from 'react'
import { MessageCircle, Heart, ChevronRight, BadgeCheck, AlertCircle } from 'lucide-react'
import Image from 'next/image'
import {
  fetchCrossDomainTimeline,
  formatLedgerPhaseLabel,
  summarizeTimelineEvents,
} from '@/lib/api/endpoints/relations'
import { fetchTrustHub } from '@/lib/api/endpoints/trust-hub'
import { getErrorMessage } from '@/lib/api/errors'
import { resolveCaseIdForTimeline } from '@/lib/auth/resolve-case'
import { getChatParticipantId, getProfileId, getUserId } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { logDataProvenance, usePageDataSource } from '@/lib/data-provenance'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'
import { mapTrustHubPendingActions } from '@/lib/trust/map-trust-hub'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { EmptyRelationships } from './ui/empty-states'
import { RelationshipsPageSkeleton } from './ui/skeletons'

interface RelationshipsPageProps {
  onOpenChat: (chatId: string) => void
  onStartVerification: () => void
}

type PendingAction = {
  id: string
  type: 'verification'
  title: string
  description: string
  icon: typeof BadgeCheck
}

export default function RelationshipsPage({ onOpenChat, onStartVerification }: RelationshipsPageProps) {
  const [activeRelationships, setActiveRelationships] = useState<Array<{
    id: string
    name: string
    stage: string
    lastMessage: string
    lastMessageTime: string
    unread: number
    verified: boolean
    image: string
  }>>([])
  const [recentActivities, setRecentActivities] = useState<Array<{ id: string; content: string; time: string; type: 'view' | 'match' | 'greeting' }>>([])
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [emptyHint, setEmptyHint] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const { usingMockData, applyProvenance } = usePageDataSource()
  const [relationPhase, setRelationPhase] = useState<string | null>(null)
  const [sourceMode, setSourceMode] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadTimeline() {
      setIsLoading(true)
      setLoadError(null)
      setEmptyHint(null)

      const timelineActorId = getUserId()
      if (!timelineActorId) {
        setIsLoading(false)
        setLoadError('请先登录后再查看关系时间线')
        return
      }

      const caseId = await resolveCaseIdForTimeline()
      const participantId = getChatParticipantId()
      if (!caseId) {
        setIsLoading(false)
        setEmptyHint('当前还没有进行中的关系')
        return
      }

      try {
        const [data, trustHub] = await Promise.all([
          fetchCrossDomainTimeline(caseId, timelineActorId),
          fetchTrustHub({ userId: timelineActorId, profileId: getProfileId() }).catch(() => null),
        ])
        if (cancelled) return

        const phaseLabel = formatLedgerPhaseLabel(data.ledger?.summary?.current_phase)
        setRelationPhase(phaseLabel)
        setSourceMode(data.source_mode || null)

        const chatConversations = data.chat?.conversations || []
        const items = chatConversations
          .filter((item) => item.conversation.channel_key === 'main_group')
          .map((item) => {
            const otherMember =
              item.conversation.members?.find(
                (member) =>
                  member.participant_id !== participantId && member.member_role !== 'agent',
              )?.participant_id || 'user-b'
            const lastMessage = item.messages[item.messages.length - 1]
            const unread =
              lastMessage && participantId && lastMessage.author_id !== participantId ? 1 : 0
            return {
              id: item.conversation.conversation_id,
              name: otherMember,
              stage: phaseLabel || (item.conversation.conversation_kind === 'group' ? '共同聊天' : '单独沟通'),
              lastMessage: lastMessage?.body || '还没有消息，试着主动开场吧',
              lastMessageTime: lastMessage?.created_at || '',
              unread,
              verified: true,
              image: PLACEHOLDER_AVATAR,
            }
          })

        setActiveRelationships(items)
        setRecentActivities(
          summarizeTimelineEvents(data.unified_timeline).length
            ? summarizeTimelineEvents(data.unified_timeline)
            : items.map((item, index) => ({
                id: String(index),
                content: `${item.name} 最近在会话里有新消息`,
                time: item.lastMessageTime || '刚刚',
                type: index % 2 === 0 ? ('greeting' as const) : ('match' as const),
              })),
        )

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

        const provenance = applyProvenance(false, items.length > 0, '/v1/ledger/timeline', data.source_mode)
        logDataProvenance('relationships', provenance)
      } catch (error) {
        if (cancelled) return
        const message = getErrorMessage(error, '关系页加载失败')
        if (message.includes('current actor is not allowed to access this match case')) {
          setEmptyHint('当前账号暂时无法查看这段关系')
        } else {
          setLoadError(message)
        }
        if (canUseMockFallback()) {
          applyProvenance(true, false, '/v1/ledger/timeline')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadTimeline()
    return () => {
      cancelled = true
    }
  }, [applyProvenance])

  if (isLoading) {
    return <RelationshipsPageSkeleton />
  }

  if (loadError && !canUseMockFallback() && activeRelationships.length === 0) {
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
          <p className="text-xs text-muted-foreground">
            {relationPhase ? `当前阶段：${relationPhase}` : '你的恋爱进行时'}
            {sourceMode === 'ledger_primary' ? ' · 统一账本' : ''}
          </p>
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
                onClick={() => onOpenChat(rel.id)}
                className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 hover:shadow-sm transition-all focus-ring animate-fade-in-up"
                style={{ animationDelay: `${index * 50}ms` }}
                aria-label={`查看与${rel.name}的对话`}
              >
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-12 h-12 rounded-full overflow-hidden">
                      <Image src={rel.image} alt={rel.name} width={48} height={48} className="object-cover" />
                    </div>
                    {rel.unread > 0 && (
                      <span className="absolute -top-1 -right-1 w-5 h-5 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center">
                        {rel.unread}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{rel.name}</span>
                      {rel.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
                      <span className="ml-auto px-2 py-0.5 bg-secondary text-[10px] rounded-full">{rel.stage}</span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate mt-0.5">{rel.lastMessage}</p>
                    <span className="text-[10px] text-muted-foreground">{rel.lastMessageTime}</span>
                  </div>
                </div>
              </button>
            ))}
            {activeRelationships.length === 0 && (
              <EmptyRelationships
                onDiscover={() => {}}
                title={emptyHint === '当前账号暂时无法查看这段关系' ? '暂时无法查看这段关系' : undefined}
                description={emptyHint || undefined}
              />
            )}
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
            关系页展示 v2 会话与 ledger 统一时间线；登录后会自动解析活跃 case_id。
          </p>
        </div>
      </div>
    </div>
  )
}
