'use client'

import { useEffect, useState } from 'react'
import { MessageCircle, Heart, Calendar, ChevronRight, BadgeCheck, AlertCircle } from 'lucide-react'
import Image from 'next/image'
import { cn } from '@/lib/utils'
import { gatewayJson, queryString } from '@/lib/gateway'
import { EmptyRelationships } from './ui/empty-states'
import { FadeIn, StaggerContainer } from './ui/animations'
import { RelationshipsPageSkeleton } from './ui/skeletons'

interface RelationshipsPageProps {
  onOpenChat: (chatId: string) => void
  onStartVerification: () => void
}

type TimelineResponse = {
  case_id: string
  requester_id: string
  conversation_count: number
  conversations: Array<{
    conversation: {
      conversation_id: string
      channel_key: string
      conversation_kind: string
      members?: Array<{
        participant_id: string
        member_role: string
      }>
    }
    messages: Array<{
      message_id: number
      author_id: string
      body: string
      created_at: string
    }>
  }>
}

const pendingActions = [
  { id: '1', type: 'feedback', title: '见面反馈', description: '与对方的进展如何？', icon: Calendar },
  { id: '2', type: 'verification', title: '完善认证', description: '补充资料认证，提升可信度', icon: BadgeCheck },
]

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

  useEffect(() => {
    const caseId = process.env.NEXT_PUBLIC_HER_CASE_ID
    const requesterId = process.env.NEXT_PUBLIC_HER_USER_ID
    if (!caseId || !requesterId) {
      return
    }

    let cancelled = false
    async function loadTimeline() {
      try {
        const data = await gatewayJson<TimelineResponse>(
          `/v2/chat/cases/${caseId}/timeline${queryString({ requester_id: requesterId })}`,
        )
        if (cancelled) return
        const items = data.conversations
          .filter((item) => item.conversation.channel_key === 'main_group')
          .map((item, index) => {
            const otherMember =
              item.conversation.members?.find(
                (member) => member.participant_id !== requesterId && member.member_role !== 'agent',
              )?.participant_id || 'user-b'
            const lastMessage = item.messages[item.messages.length - 1]
            return {
              id: item.conversation.conversation_id,
              name: otherMember,
              stage: item.conversation.conversation_kind === 'group' ? '共同聊天' : '单独沟通',
              lastMessage: lastMessage?.body || '还没有消息，试着主动开场吧',
              lastMessageTime: lastMessage?.created_at || '',
              unread: 0,
              verified: true,
              image:
                index % 2 === 0
                  ? 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face'
                  : 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=200&h=200&fit=crop&crop=face',
            }
          })
        setActiveRelationships(items)
        setRecentActivities(
          items.map((item, index) => ({
            id: String(index),
            content: `${item.name} 最近在会话里有新消息`,
            time: item.lastMessageTime || '刚刚',
            type: index % 2 === 0 ? 'greeting' : 'match',
          })),
        )
      } catch {
        // Keep empty state when timeline is unavailable.
      }
    }

    void loadTimeline()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex flex-col h-full bg-background">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="text-lg font-medium">关系</h1>
          <p className="text-xs text-muted-foreground">你的恋爱进行时</p>
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
              <EmptyRelationships onDiscover={() => {}} />
            )}
          </div>
        </section>

        <section>
          <h2 className="text-sm font-medium mb-2">待处理</h2>
          <div className="space-y-2">
            {pendingActions.map((action) => {
              const Icon = action.icon
              return (
                <button
                  key={action.id}
                  onClick={action.type === 'verification' ? onStartVerification : undefined}
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
            关系页现在展示的是 `v2 chat` 真实 timeline；如果你看不到会话，优先检查 `NEXT_PUBLIC_HER_CASE_ID` 和 `NEXT_PUBLIC_HER_USER_ID`。
          </p>
        </div>
      </div>
    </div>
  )
}
