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
    matchReason: '她热爱设计与旅行，性格温和细腻。你们在审美品味和生活态度上有很高的契合度。',
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
    matchReason: '她对生活充满热情，喜欢阅读和咖啡。你们的价值观和兴趣爱好非常相似。',
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
    matchReason: '她有着独特的艺术气质，向往简单纯粹的生活。虽然异地，但生活态度高度契合。',
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
    matchReason: '她理性而浪漫，追求高品质生活。对未来家庭有清晰规划，目标明确。',
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
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
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
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="editorial-title text-2xl text-foreground">推荐</h1>
                <p className="text-xs text-muted-foreground mt-0.5">平台为你精心挑选的人选</p>
              </div>
              {unreadCount > 0 && (
                <div className="px-3 py-1 bg-primary/10 rounded-full">
                  <span className="text-xs font-medium text-primary">{unreadCount}位新推荐</span>
                </div>
              )}
            </div>
          </div>

          {/* Filter tabs */}
          <div className="px-5 pb-3 flex gap-2">
            {[
              { id: 'all' as FilterType, label: '全部' },
              { id: 'unread' as FilterType, label: '未读' },
              { id: 'saved' as FilterType, label: '已保存' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setFilter(tab.id)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  filter === tab.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary/60 text-muted-foreground hover:bg-secondary'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Recommendations list */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {filteredRecommendations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-full bg-secondary flex items-center justify-center mb-4">
              <Sparkles className="w-7 h-7 text-muted-foreground" />
            </div>
            <p className="text-muted-foreground">暂无推荐</p>
          </div>
        ) : (
          filteredRecommendations.map((candidate) => (
            <div
              key={candidate.id}
              onClick={() => onViewCandidate(candidate.id)}
              className="w-full bg-card rounded-3xl overflow-hidden shadow-soft border border-border/50 transition-all duration-300 hover:shadow-elevated active:scale-[0.99] text-left cursor-pointer"
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onViewCandidate(candidate.id)
                }
              }}
            >
              <div className="flex gap-4 p-4">
                {/* Image */}
                <div className="relative w-28 h-36 shrink-0 rounded-2xl overflow-hidden">
                  <Image
                    src={candidate.image}
                    alt={candidate.name}
                    fill
                    className="object-cover"
                  />
                  {/* New badge */}
                  {candidate.isNew && (
                    <div className="absolute top-2 left-2 px-2 py-0.5 bg-rose rounded-full">
                      <span className="text-[10px] font-medium text-white">新</span>
                    </div>
                  )}
                  {/* Match score */}
                  <div className="absolute bottom-2 left-2 px-2 py-0.5 bg-gold/90 rounded-full">
                    <span className="text-[10px] font-semibold text-foreground">{candidate.matchScore}%</span>
                  </div>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0 py-1">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-medium text-foreground">{candidate.name}，{candidate.age}</h3>
                    {candidate.verified && (
                      <BadgeCheck className="w-4 h-4 text-primary shrink-0" />
                    )}
                  </div>
                  
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground mb-3">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      {candidate.city}
                    </span>
                    <span className="flex items-center gap-1">
                      <Briefcase className="w-3 h-3" />
                      {candidate.occupation}
                    </span>
                    <span className="flex items-center gap-1">
                      <GraduationCap className="w-3 h-3" />
                      {candidate.education}
                    </span>
                  </div>

                  {/* Match reason */}
                  <div className="bg-blush/50 rounded-xl px-3 py-2 mb-3">
                    <p className="text-xs text-taupe leading-relaxed line-clamp-2">
                      <Sparkles className="w-3 h-3 inline mr-1 text-gold" />
                      {candidate.matchReason}
                    </p>
                  </div>

                  {/* Time and actions */}
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {candidate.recommendedAt}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => dismiss(candidate.id, e)}
                        className="w-8 h-8 rounded-full bg-secondary/60 flex items-center justify-center hover:bg-secondary transition-colors"
                      >
                        <X className="w-4 h-4 text-muted-foreground" />
                      </button>
                      <button
                        onClick={(e) => toggleSave(candidate.id, e)}
                        className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
                          savedIds.has(candidate.id)
                            ? 'bg-gold/20'
                            : 'bg-secondary/60 hover:bg-secondary'
                        }`}
                      >
                        <Bookmark 
                          className={`w-4 h-4 ${
                            savedIds.has(candidate.id) ? 'text-gold fill-gold' : 'text-muted-foreground'
                          }`} 
                        />
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* View detail hint */}
              <div className="px-4 py-2.5 border-t border-border/30 flex items-center justify-center gap-1 text-primary text-xs font-medium">
                查看详细资料
                <ChevronRight className="w-3.5 h-3.5" />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
