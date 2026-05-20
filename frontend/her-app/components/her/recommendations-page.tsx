'use client'

import { useState } from 'react'
import { Sparkles, MapPin, Briefcase, GraduationCap, BadgeCheck, Bookmark, X, Clock, ChevronRight } from 'lucide-react'
import Image from 'next/image'

interface RecommendationsPageProps {
  onViewCandidate: (candidateId: string) => void
}

const recommendations = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    education: '复旦大学',
    matchScore: 95,
    verified: true,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=500&fit=crop&crop=face',
    matchReason: '审美品味和生活态度高度契合',
    isNew: true,
    recommendedAt: '今天 10:30',
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
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=400&h=500&fit=crop&crop=face',
    matchReason: '价值观和兴趣爱好非常相似',
    isNew: true,
    recommendedAt: '今天 09:15',
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
    image: 'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=400&h=500&fit=crop&crop=face',
    matchReason: '生活态度高度契合',
    isNew: false,
    recommendedAt: '昨天 16:45',
  },
  {
    id: '4',
    name: '张雨',
    age: 29,
    city: '北京',
    occupation: '建筑师',
    education: '清华大学',
    matchScore: 85,
    verified: true,
    image: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&h=500&fit=crop&crop=face',
    matchReason: '对未来家庭有清晰规划',
    isNew: false,
    recommendedAt: '昨天 11:20',
  },
]

type FilterType = 'all' | 'unread' | 'saved'

export default function RecommendationsPage({ onViewCandidate }: RecommendationsPageProps) {
  const [filter, setFilter] = useState<FilterType>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set(['3']))
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())

  const toggleSave = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSavedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const dismiss = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setDismissedIds(prev => new Set(prev).add(id))
  }

  const filteredRecommendations = recommendations.filter(r => {
    if (dismissedIds.has(r.id)) return false
    if (filter === 'unread') return r.isNew
    if (filter === 'saved') return savedIds.has(r.id)
    return true
  })

  const unreadCount = recommendations.filter(r => r.isNew && !dismissedIds.has(r.id)).length

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-medium">推荐</h1>
              <p className="text-xs text-muted-foreground">为你精心挑选的人选</p>
            </div>
            {unreadCount > 0 && (
              <span className="px-2 py-1 bg-primary/10 text-primary text-xs font-medium rounded-full">
                {unreadCount}位新推荐
              </span>
            )}
          </div>
        </div>

        {/* Filter tabs */}
        <div className="px-4 pb-3 flex gap-2">
          {[
            { id: 'all' as FilterType, label: '全部' },
            { id: 'unread' as FilterType, label: '未读' },
            { id: 'saved' as FilterType, label: '已保存' },
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
      </header>

      {/* Recommendations list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 pb-20">
        {filteredRecommendations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-14 h-14 rounded-full bg-secondary flex items-center justify-center mb-3">
              <Sparkles className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">暂无推荐</p>
          </div>
        ) : (
          filteredRecommendations.map((candidate) => (
            <button
              key={candidate.id}
              onClick={() => onViewCandidate(candidate.id)}
              className="w-full bg-card border border-border rounded-xl text-left hover:border-primary/30 transition-colors"
            >
              <div className="flex gap-3 p-3">
                {/* Image */}
                <div className="relative w-20 h-24 shrink-0 rounded-lg overflow-hidden">
                  <Image src={candidate.image} alt={candidate.name} fill className="object-cover" />
                  {candidate.isNew && (
                    <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-rose text-[10px] font-medium text-white rounded">新</span>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0 py-0.5">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium">{candidate.name}，{candidate.age}</span>
                    {candidate.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
                    <span className="ml-auto text-sm font-medium text-primary">{candidate.matchScore}%</span>
                  </div>
                  
                  <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground mb-2">
                    <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{candidate.city}</span>
                    <span>{candidate.occupation}</span>
                  </div>

                  <p className="text-xs text-muted-foreground mb-2">{candidate.matchReason}</p>

                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" />{candidate.recommendedAt}
                    </span>
                    <div className="flex items-center gap-1">
                      <span onClick={(e) => dismiss(candidate.id, e)} className="w-7 h-7 rounded-full bg-secondary flex items-center justify-center">
                        <X className="w-3.5 h-3.5 text-muted-foreground" />
                      </span>
                      <span onClick={(e) => toggleSave(candidate.id, e)} className={`w-7 h-7 rounded-full flex items-center justify-center ${savedIds.has(candidate.id) ? 'bg-gold/20' : 'bg-secondary'}`}>
                        <Bookmark className={`w-3.5 h-3.5 ${savedIds.has(candidate.id) ? 'text-gold fill-gold' : 'text-muted-foreground'}`} />
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="px-3 py-2 border-t border-border flex items-center justify-center gap-1 text-primary text-xs">
                查看详细资料 <ChevronRight className="w-3 h-3" />
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  )
}
