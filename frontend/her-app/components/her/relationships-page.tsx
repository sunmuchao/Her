'use client'

import { MessageCircle, Heart, Calendar, ChevronRight, BadgeCheck, AlertCircle } from 'lucide-react'
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
    lastMessage: '那家咖啡店的环境真的很不错',
    lastMessageTime: '2小时前',
    unread: 0,
    verified: true,
  },
]

const pendingActions = [
  { id: '1', type: 'feedback', title: '见面反馈', description: '与林悦的见面还顺利吗？', icon: Calendar },
  { id: '2', type: 'verification', title: '完善认证', description: '补充学历认证，提升可信度', icon: BadgeCheck },
]

const recentActivities = [
  { id: '1', content: '林悦查看了你的资料', time: '1小时前', type: 'view' },
  { id: '2', content: '你们的匹配度提升到了95%', time: '3小时前', type: 'match' },
  { id: '3', content: '陈思对你发起了主动招呼', time: '昨天', type: 'greeting' },
]

export default function RelationshipsPage({ onOpenChat, onStartVerification }: RelationshipsPageProps) {
  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="text-lg font-medium">关系</h1>
          <p className="text-xs text-muted-foreground">你的恋爱进行时</p>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5 pb-20">
        {/* Active relationships */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium">正在进行中</h2>
            <span className="text-xs text-muted-foreground">{activeRelationships.length}位</span>
          </div>
          <div className="space-y-3">
            {activeRelationships.map((rel) => (
              <button
                key={rel.id}
                onClick={() => onOpenChat(rel.id)}
                className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 transition-colors"
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
                      <span className="font-medium">{rel.name}，{rel.age}</span>
                      {rel.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
                      <span className="ml-auto px-2 py-0.5 bg-secondary text-[10px] rounded-full">{rel.stage}</span>
                    </div>
                    <p className="text-sm text-muted-foreground truncate mt-0.5">{rel.lastMessage}</p>
                    <span className="text-[10px] text-muted-foreground">{rel.lastMessageTime}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>

        {/* Pending actions */}
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

        {/* Recent activity */}
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

        {/* Tip */}
        <div className="bg-secondary rounded-xl p-3 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
          <p className="text-xs text-muted-foreground leading-relaxed">
            保持适度的沟通频率，让关系自然发展。如有疑虑，可随时联系红娘。
          </p>
        </div>
      </div>
    </div>
  )
}
