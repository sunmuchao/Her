'use client'

import { MessageCircle, Heart, Calendar, AlertCircle, ChevronRight, BadgeCheck } from 'lucide-react'
import Image from 'next/image'

interface RelationshipsPageProps {
  onOpenChat: (chatId: string) => void
  onStartVerification: () => void
}

const activeRelationships = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
    stage: '初步了解',
    stageColor: 'rose',
    lastMessage: '好的，那我们周六见面聊聊吧',
    lastMessageTime: '刚刚',
    unread: 2,
    verified: true,
  },
  {
    id: '2',
    name: '陈思',
    age: 27,
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=200&h=200&fit=crop&crop=face',
    stage: '持续沟通',
    stageColor: 'gold',
    lastMessage: '那家咖啡店的环境真的很不错',
    lastMessageTime: '2小时前',
    unread: 0,
    verified: true,
  },
]

const pendingActions = [
  {
    id: '1',
    type: 'feedback',
    title: '见面反馈',
    description: '与林悦的见面还顺利吗？',
    icon: Calendar,
    actionText: '填写反馈',
  },
  {
    id: '2',
    type: 'verification',
    title: '完善认证',
    description: '补充学历认证，提升可信度',
    icon: BadgeCheck,
    actionText: '立即认证',
  },
]

const recentActivities = [
  {
    id: '1',
    content: '林悦查看了你的资料',
    time: '1小时前',
    type: 'view',
  },
  {
    id: '2',
    content: '你们的匹配度提升到了95%',
    time: '3小时前',
    type: 'match',
  },
  {
    id: '3',
    content: '陈思对你发起了主动招呼',
    time: '昨天',
    type: 'greeting',
  },
]

export default function RelationshipsPage({ onOpenChat, onStartVerification }: RelationshipsPageProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <h1 className="editorial-title text-2xl text-foreground">关系</h1>
            <p className="text-xs text-muted-foreground mt-0.5">你的恋爱进行时</p>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {/* Active relationships */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-foreground">正在进行中</h2>
            <span className="text-xs text-muted-foreground">{activeRelationships.length}位</span>
          </div>

          <div className="space-y-3">
            {activeRelationships.map((relationship) => (
              <button
                key={relationship.id}
                onClick={() => onOpenChat(relationship.id)}
                className="w-full bg-card rounded-2xl p-4 shadow-soft border border-border/50 transition-all hover:shadow-elevated active:scale-[0.99] text-left"
              >
                <div className="flex items-start gap-3">
                  {/* Avatar */}
                  <div className="relative">
                    <div className="w-14 h-14 rounded-full overflow-hidden border-2 border-rose-soft">
                      <Image
                        src={relationship.image}
                        alt={relationship.name}
                        width={56}
                        height={56}
                        className="object-cover"
                      />
                    </div>
                    {relationship.unread > 0 && (
                      <div className="absolute -top-1 -right-1 w-5 h-5 bg-primary rounded-full flex items-center justify-center">
                        <span className="text-[10px] font-medium text-primary-foreground">{relationship.unread}</span>
                      </div>
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-medium text-foreground">{relationship.name}，{relationship.age}</h3>
                      {relationship.verified && (
                        <BadgeCheck className="w-4 h-4 text-primary shrink-0" />
                      )}
                      <span className={`ml-auto px-2 py-0.5 rounded-full text-[10px] font-medium ${
                        relationship.stageColor === 'rose' 
                          ? 'bg-rose-soft text-rose' 
                          : 'bg-gold-soft text-gold'
                      }`}>
                        {relationship.stage}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate">{relationship.lastMessage}</p>
                    <span className="text-[10px] text-muted-foreground/70 mt-1 block">{relationship.lastMessageTime}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Pending actions */}
        <section>
          <h2 className="text-sm font-medium text-foreground mb-3">待处理事项</h2>
          <div className="space-y-3">
            {pendingActions.map((action) => {
              const Icon = action.icon
              return (
                <button
                  key={action.id}
                  onClick={action.type === 'verification' ? onStartVerification : undefined}
                  className="w-full bg-gradient-to-r from-blush/60 to-card rounded-2xl p-4 shadow-soft border border-rose-soft/30 transition-all hover:shadow-elevated active:scale-[0.99] text-left"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-rose-soft/50 flex items-center justify-center">
                      <Icon className="w-5 h-5 text-primary" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-foreground">{action.title}</h3>
                      <p className="text-xs text-muted-foreground">{action.description}</p>
                    </div>
                    <div className="flex items-center gap-1 text-primary text-xs font-medium">
                      {action.actionText}
                      <ChevronRight className="w-4 h-4" />
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </section>

        {/* Recent activity */}
        <section>
          <h2 className="text-sm font-medium text-foreground mb-3">最近动态</h2>
          <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
            {recentActivities.map((activity, index) => (
              <div
                key={activity.id}
                className={`px-4 py-3 flex items-center gap-3 ${
                  index !== recentActivities.length - 1 ? 'border-b border-border/30' : ''
                }`}
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  activity.type === 'view' ? 'bg-secondary' :
                  activity.type === 'match' ? 'bg-gold-soft' : 'bg-rose-soft'
                }`}>
                  {activity.type === 'view' && <MessageCircle className="w-4 h-4 text-muted-foreground" />}
                  {activity.type === 'match' && <Heart className="w-4 h-4 text-gold" />}
                  {activity.type === 'greeting' && <Heart className="w-4 h-4 text-rose fill-rose" />}
                </div>
                <div className="flex-1">
                  <p className="text-sm text-foreground">{activity.content}</p>
                  <span className="text-[10px] text-muted-foreground">{activity.time}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Tip */}
        <div className="bg-blush/40 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-taupe shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-taupe leading-relaxed">
              保持适度的沟通频率，让关系自然发展。如有任何疑虑，可随时联系红娘小雅。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
