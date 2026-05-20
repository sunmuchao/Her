'use client'

import { useState, useEffect, useRef } from 'react'
import { Send, Sparkles, MapPin, Briefcase, GraduationCap, BadgeCheck, ChevronRight, Mail, Clock, X, Bookmark, Search, ArrowLeft } from 'lucide-react'
import Image from 'next/image'
import { TypingIndicator } from './ui/typing-indicator'
import { EmptyRecommendations, EmptySearchResults } from './ui/empty-states'
import { InboxItemSkeleton } from './ui/skeletons'

interface DiscoverPageProps {
  onViewCandidate: (candidateId: string) => void
  onOpenInbox: () => void
  inboxUnreadCount?: number
}

const initialMessages = [
  {
    id: '1',
    type: 'matchmaker' as const,
    content: '你好，我是你的专属红娘小雅。接下来我会帮你找到那个对的人。',
    timestamp: '09:30',
  },
  {
    id: '2',
    type: 'matchmaker' as const,
    content: '你理想中的伴侣是什么样的？',
    timestamp: '09:31',
  },
  {
    id: '3',
    type: 'user' as const,
    content: '希望对方性格温柔，有稳定的工作，最好在同一个城市',
    timestamp: '09:35',
  },
  {
    id: '4',
    type: 'matchmaker' as const,
    content: '好的，根据你的期待，我为你挑选了几位优秀的人选。',
    timestamp: '09:40',
  },
]

const recommendedCandidates = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    education: '复旦大学',
    matchScore: 95,
    verified: true,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=600&fit=crop&crop=face',
    matchReason: '性格温和、同城、审美品味相近',
  },
  {
    id: '2',
    name: '陈思',
    age: 27,
    city: '上海',
    occupation: '品牌策划',
    education: '浙江大学',
    matchScore: 92,
    verified: true,
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=400&h=600&fit=crop&crop=face',
    matchReason: '价值观相似、兴趣爱好匹配',
  },
  {
    id: '3',
    name: '王晴',
    age: 26,
    city: '杭州',
    occupation: '插画师',
    education: '中国美院',
    matchScore: 88,
    verified: true,
    image: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=400&h=600&fit=crop&crop=face',
    matchReason: '艺术气质、生活态度契合',
  },
]

const currentPreferences = ['同城优先', '本科以上', '年龄相近', '性格温柔']

export default function DiscoverPage({ onViewCandidate, onOpenInbox, inboxUnreadCount = 3 }: DiscoverPageProps) {
  const [messages] = useState(initialMessages)
  const [inputValue, setInputValue] = useState('')
  const [showCandidates, setShowCandidates] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = setTimeout(() => setShowCandidates(true), 500)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsTyping(true)
      setTimeout(() => setIsTyping(false), 2500)
    }, 1500)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (isTyping && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [isTyping])

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header - clean, no excessive blur/gradient */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h1 className="font-medium text-foreground">小雅</h1>
                <p className="text-xs text-muted-foreground">你的专属红娘</p>
              </div>
            </div>
            
            {/* Inbox button - simple, clear */}
            <button 
              onClick={onOpenInbox}
              className="relative flex items-center gap-2 px-3 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors"
            >
              <Mail className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm">来信</span>
              {inboxUnreadCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center">
                  {inboxUnreadCount}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Preferences - simple tags */}
      <div className="px-4 py-2 flex gap-2 overflow-x-auto border-b border-border">
        {currentPreferences.map((pref, i) => (
          <span key={i} className="shrink-0 px-2.5 py-1 bg-secondary text-muted-foreground text-xs rounded-md">
            {pref}
          </span>
        ))}
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-4 py-4 space-y-4">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] ${msg.type === 'user' ? 'order-1' : ''}`}>
                <div className={`px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
                  msg.type === 'user' 
                    ? 'bg-primary text-primary-foreground rounded-br-md' 
                    : 'bg-card border border-border rounded-bl-md'
                }`}>
                  {msg.content}
                </div>
                <p className={`text-[10px] text-muted-foreground mt-1 ${msg.type === 'user' ? 'text-right' : ''}`}>
                  {msg.timestamp}
                </p>
              </div>
            </div>
          ))}

          {isTyping && <TypingIndicator name="小雅" />}
          <div ref={chatEndRef} />

          {/* Candidate cards - clean, focused */}
          {showCandidates && (
            <div className="pt-4">
              <p className="text-xs text-muted-foreground mb-3">为你精心挑选</p>
              <div className="space-y-3">
                {recommendedCandidates.map((candidate, index) => (
                  <button
                    key={candidate.id}
                    onClick={() => onViewCandidate(candidate.id)}
                    className="w-full bg-card border border-border rounded-xl p-3 text-left hover:border-primary/30 transition-colors"
                    style={{ animationDelay: `${index * 100}ms` }}
                  >
                    <div className="flex gap-3">
                      <div className="relative w-16 h-20 rounded-lg overflow-hidden shrink-0">
                        <Image
                          src={candidate.image}
                          alt={candidate.name}
                          fill
                          className="object-cover"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">{candidate.name}</span>
                          <span className="text-sm text-muted-foreground">{candidate.age}岁</span>
                          {candidate.verified && (
                            <BadgeCheck className="w-4 h-4 text-primary" />
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3 h-3" />{candidate.city}
                          </span>
                          <span>{candidate.occupation}</span>
                        </div>
                        <p className="text-xs text-primary mt-2">{candidate.matchReason}</p>
                      </div>
                      <div className="flex flex-col items-end justify-between">
                        <span className="text-sm font-medium text-primary">{candidate.matchScore}%</span>
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input - simple */}
      <div className="sticky bottom-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="输入你的想法..."
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
          />
          <button className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <Send className="w-4 h-4 text-primary-foreground" />
          </button>
        </div>
      </div>
    </div>
  )
}

// Inbox data
const inboxItems = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    matchScore: 95,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
    type: 'delayed' as const,
    message: '她符合你的期待，性格温和，同在上海',
    time: '2小时前',
    isRead: false,
  },
  {
    id: '2',
    name: '陈思',
    age: 27,
    city: '上海',
    occupation: '品牌策划',
    matchScore: 92,
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=200&h=200&fit=crop&crop=face',
    type: 'matched' as const,
    message: '你们的价值观很契合',
    time: '昨天',
    isRead: false,
  },
  {
    id: '3',
    name: '王晴',
    age: 26,
    city: '杭州',
    occupation: '插画师',
    matchScore: 88,
    image: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=200&h=200&fit=crop&crop=face',
    type: 'delayed' as const,
    message: '虽然异地，但你们的艺术品味非常相近',
    time: '2天前',
    isRead: true,
  },
  {
    id: '4',
    name: '张雨',
    age: 29,
    city: '北京',
    occupation: '建筑师',
    matchScore: 85,
    image: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200&h=200&fit=crop&crop=face',
    type: 'matched' as const,
    message: '她对未来家庭有清晰的规划',
    time: '3天前',
    isRead: true,
  },
]

export function RecommendationInbox({ 
  onViewCandidate, 
  onBack 
}: { 
  onViewCandidate: (candidateId: string) => void
  onBack: () => void
}) {
  const [filter, setFilter] = useState<'all' | 'delayed' | 'matched'>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set(['3']))
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 600)
    return () => clearTimeout(timer)
  }, [])

  const filteredItems = inboxItems.filter(item => {
    if (dismissedIds.has(item.id)) return false
    if (filter === 'delayed') return item.type === 'delayed'
    if (filter === 'matched') return item.type === 'matched'
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return item.name.toLowerCase().includes(q) || 
             item.city.toLowerCase().includes(q) || 
             item.occupation.toLowerCase().includes(q)
    }
    return true
  })

  const handleSave = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setSavedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleDismiss = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setDismissedIds(prev => new Set(prev).add(id))
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center gap-3">
            <button onClick={onBack} className="w-8 h-8 flex items-center justify-center">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="font-medium">推荐来信</h1>
          </div>
        </div>

        {/* Filters */}
        <div className="px-4 pb-3 flex gap-2">
          {[
            { id: 'all' as const, label: '全部' },
            { id: 'delayed' as const, label: '延迟推荐' },
            { id: 'matched' as const, label: '主动撮合' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                filter === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-muted-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索姓名、城市、职业..."
              className="w-full pl-9 pr-8 py-2 bg-secondary rounded-lg text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {isLoading ? (
          <>
            <InboxItemSkeleton />
            <InboxItemSkeleton />
            <InboxItemSkeleton />
          </>
        ) : filteredItems.length === 0 ? (
          searchQuery ? <EmptySearchResults keyword={searchQuery} /> : <EmptyRecommendations onRefresh={onBack} />
        ) : (
          filteredItems.map((item) => (
            <div
              key={item.id}
              onClick={() => onViewCandidate(item.id)}
              className="bg-card border border-border rounded-xl p-3 cursor-pointer hover:border-primary/30 transition-colors"
            >
              <div className="flex gap-3">
                <div className="relative w-14 h-14 rounded-lg overflow-hidden shrink-0">
                  <Image src={item.image} alt={item.name} fill className="object-cover" />
                  {!item.isRead && (
                    <div className="absolute top-1 right-1 w-2 h-2 bg-rose rounded-full" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.name}</span>
                      <span className="text-xs text-muted-foreground">{item.age}岁 · {item.city}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{item.time}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{item.occupation}</p>
                  <p className="text-sm text-foreground mt-1.5 line-clamp-1">{item.message}</p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-border">
                <div className="flex items-center gap-1">
                  <span className={`px-2 py-0.5 rounded text-[10px] ${
                    item.type === 'delayed' ? 'bg-gold/20 text-gold' : 'bg-rose/20 text-rose'
                  }`}>
                    {item.type === 'delayed' ? '延迟推荐' : '主动撮合'}
                  </span>
                  <span className="text-xs text-primary font-medium">{item.matchScore}% 匹配</span>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => handleDismiss(e, item.id)}
                    className="p-1.5 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                  <button
                    onClick={(e) => handleSave(e, item.id)}
                    className={`p-1.5 transition-colors ${savedIds.has(item.id) ? 'text-gold' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    <Bookmark className={`w-4 h-4 ${savedIds.has(item.id) ? 'fill-current' : ''}`} />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
