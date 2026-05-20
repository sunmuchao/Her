'use client'

import { useState, useEffect } from 'react'
import { Send, Sparkles, MapPin, Briefcase, GraduationCap, BadgeCheck, ChevronRight, Heart } from 'lucide-react'
import Image from 'next/image'

interface DiscoverPageProps {
  onViewCandidate: (candidateId: string) => void
}

// Mock conversation data
const initialMessages = [
  {
    id: '1',
    type: 'matchmaker' as const,
    content: '你好，很高兴认识你。我是你的专属红娘小雅，接下来我会帮你找到那个对的人。',
    timestamp: '09:30',
  },
  {
    id: '2',
    type: 'matchmaker' as const,
    content: '在开始之前，我想先了解一下你。你理想中的伴侣是什么样的？',
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
    content: '明白了，温柔、稳定、同城，这些都是很好的期待。关于年龄和学历，你有什么想法吗？',
    timestamp: '09:36',
  },
  {
    id: '5',
    type: 'user' as const,
    content: '年龄相差不要太大，本科以上就好',
    timestamp: '09:38',
  },
  {
    id: '6',
    type: 'matchmaker' as const,
    content: '好的，我已经记下了。根据你的期待，我为你挑选了几位很优秀的人选。他们都经过了真实性认证，可以放心了解。',
    timestamp: '09:40',
  },
]

// Mock candidate data with richer profiles
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
    personality: '温柔细腻',
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
    personality: '独立自信',
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
    personality: '浪漫文艺',
  },
]

const currentPreferences = [
  '同城优先',
  '本科以上',
  '年龄相近',
  '性格温柔',
]

export default function DiscoverPage({ onViewCandidate }: DiscoverPageProps) {
  const [messages] = useState(initialMessages)
  const [inputValue, setInputValue] = useState('')
  const [showCandidates, setShowCandidates] = useState(false)
  const [revealCards, setRevealCards] = useState(false)
  const [hoveredCard, setHoveredCard] = useState<string | null>(null)

  // Dramatic reveal animation for candidates
  useEffect(() => {
    const timer1 = setTimeout(() => setShowCandidates(true), 300)
    const timer2 = setTimeout(() => setRevealCards(true), 800)
    return () => {
      clearTimeout(timer1)
      clearTimeout(timer2)
    }
  }, [])

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-background via-background to-blush/20">
      {/* Premium Header with depth */}
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="relative">
          {/* Blur backdrop */}
          <div className="absolute inset-0 bg-background/80 backdrop-blur-xl" />
          {/* Subtle gradient overlay */}
          <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/10 to-transparent" />
          {/* Content */}
          <div className="relative px-5 py-4 border-b border-border/20">
            <div className="flex items-center gap-4">
              {/* Matchmaker avatar with premium styling */}
              <div className="relative">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#c8a888] via-[#d4b89a] to-[#b89878] p-[2px] shadow-lg">
                  <div className="w-full h-full rounded-full bg-gradient-to-br from-gold-soft to-gold flex items-center justify-center">
                    <Sparkles className="w-5 h-5 text-foreground" strokeWidth={1.5} />
                  </div>
                </div>
                {/* Online indicator */}
                <div className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-green-500 rounded-full border-2 border-background" />
              </div>
              <div>
                <h1 className="font-semibold text-foreground text-lg">小雅</h1>
                <p className="text-xs text-muted-foreground">你的专属红娘 · 正在为你寻找</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Preference chips - refined styling */}
      <div className="px-5 py-3 flex gap-2 overflow-x-auto scrollbar-hide">
        <div className="flex items-center gap-1 shrink-0 pr-3">
          <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          <span className="text-[11px] text-muted-foreground">已理解偏好</span>
        </div>
        {currentPreferences.map((pref, index) => (
          <span
            key={index}
            className="shrink-0 px-3 py-1.5 bg-gradient-to-r from-blush/80 to-rose-soft/60 text-taupe text-xs rounded-full border border-rose-soft/50 shadow-sm"
          >
            {pref}
          </span>
        ))}
      </div>

      {/* Chat timeline with refined message styling */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {messages.map((message, index) => (
          <div
            key={message.id}
            className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
            style={{ 
              animationDelay: `${index * 100}ms`,
              animation: 'fadeInUp 0.5s ease-out forwards'
            }}
          >
            <div
              className={`max-w-[80%] ${
                message.type === 'user'
                  ? 'bg-gradient-to-br from-primary to-rose text-primary-foreground rounded-3xl rounded-br-lg shadow-md'
                  : 'bg-card/90 backdrop-blur-sm text-card-foreground rounded-3xl rounded-bl-lg shadow-soft border border-border/30'
              } px-4 py-3`}
            >
              <p className="text-sm leading-relaxed">{message.content}</p>
              <span className={`text-[10px] mt-1 block ${
                message.type === 'user' ? 'text-primary-foreground/60' : 'text-muted-foreground'
              }`}>
                {message.timestamp}
              </span>
            </div>
          </div>
        ))}

        {/* DRAMATIC Candidate recommendations reveal */}
        {showCandidates && (
          <div className="py-6">
            {/* Section intro with dramatic reveal */}
            <div 
              className={`mb-6 transition-all duration-700 ${
                revealCards ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
              }`}
            >
              <div className="flex items-center gap-3 mb-2">
                <div className="flex-1 h-px bg-gradient-to-r from-transparent via-rose-soft/60 to-transparent" />
                <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blush/50 via-rose-soft/30 to-blush/50 rounded-full">
                  <Sparkles className="w-4 h-4 text-gold" />
                  <span className="text-sm font-medium text-foreground">为你精心挑选</span>
                </div>
                <div className="flex-1 h-px bg-gradient-to-r from-transparent via-rose-soft/60 to-transparent" />
              </div>
              <p className="text-center text-sm text-muted-foreground">
                根据你的期待，从 <span className="text-primary font-medium">1,247</span> 位优质用户中为你找到
              </p>
            </div>

            {/* Premium card container */}
            <div 
              className={`relative rounded-[28px] overflow-hidden transition-all duration-1000 ${
                revealCards ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
              }`}
            >
              {/* Luxurious background */}
              <div className="absolute inset-0 bg-gradient-to-br from-card via-blush/20 to-rose-soft/30" />
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-gold-soft/20 via-transparent to-transparent" />
              
              {/* Decorative corner accents */}
              <div className="absolute top-0 left-0 w-32 h-32 bg-gradient-to-br from-rose-soft/30 to-transparent rounded-br-full" />
              <div className="absolute bottom-0 right-0 w-40 h-40 bg-gradient-to-tl from-gold-soft/20 to-transparent rounded-tl-full" />
              
              {/* Content */}
              <div className="relative p-5">
                {/* Header */}
                <div className="flex items-center justify-between mb-5">
                  <div className="flex items-center gap-2">
                    <Heart className="w-4 h-4 text-rose fill-rose/30" />
                    <span className="text-sm text-foreground font-medium">今日推荐</span>
                  </div>
                  <span className="text-xs text-muted-foreground">3位优质人选</span>
                </div>

                {/* Horizontal scrolling candidates - PREMIUM CARD DESIGN */}
                <div className="overflow-x-auto scrollbar-hide -mx-1 px-1 pb-2">
                  <div className="flex gap-4" style={{ width: 'max-content' }}>
                    {recommendedCandidates.map((candidate, index) => (
                      <button
                        key={candidate.id}
                        onClick={() => onViewCandidate(candidate.id)}
                        onMouseEnter={() => setHoveredCard(candidate.id)}
                        onMouseLeave={() => setHoveredCard(null)}
                        className={`relative w-52 shrink-0 bg-background rounded-2xl overflow-hidden shadow-elevated transition-all duration-500 text-left group ${
                          revealCards ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-12'
                        } ${hoveredCard === candidate.id ? 'scale-[1.02] shadow-2xl' : ''}`}
                        style={{ 
                          transitionDelay: `${index * 150 + 200}ms`,
                        }}
                      >
                        {/* Image container with cinematic treatment */}
                        <div className="relative h-64 overflow-hidden">
                          <Image
                            src={candidate.image}
                            alt={candidate.name}
                            fill
                            className="object-cover transition-transform duration-700 group-hover:scale-105"
                          />
                          
                          {/* Cinematic gradient overlays */}
                          <div className="absolute inset-0 bg-gradient-to-t from-foreground/90 via-foreground/20 to-transparent" />
                          <div className="absolute inset-0 bg-gradient-to-br from-rose/10 via-transparent to-gold/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                          
                          {/* Match score - premium badge */}
                          <div className="absolute top-3 right-3">
                            <div className="relative">
                              <div className="absolute inset-0 bg-gold/50 rounded-full blur-md" />
                              <div className="relative px-3 py-1.5 bg-gradient-to-r from-gold via-[#d4b89a] to-gold rounded-full flex items-center gap-1.5 shadow-lg">
                                <Sparkles className="w-3 h-3 text-foreground" />
                                <span className="text-xs font-bold text-foreground">{candidate.matchScore}%</span>
                              </div>
                            </div>
                          </div>

                          {/* Verified badge */}
                          {candidate.verified && (
                            <div className="absolute top-3 left-3 w-8 h-8 bg-background/95 rounded-full flex items-center justify-center shadow-lg backdrop-blur-sm">
                              <BadgeCheck className="w-5 h-5 text-primary" />
                            </div>
                          )}

                          {/* Name and basic info overlay */}
                          <div className="absolute bottom-0 left-0 right-0 p-4 text-white">
                            <div className="flex items-baseline gap-2 mb-1">
                              <h3 className="editorial-title text-2xl">{candidate.name}</h3>
                              <span className="text-lg text-white/80">{candidate.age}</span>
                            </div>
                            <div className="flex items-center gap-1.5 text-white/70">
                              <MapPin className="w-3 h-3" />
                              <span className="text-sm">{candidate.city}</span>
                              <span className="text-white/40">·</span>
                              <span className="text-sm">{candidate.personality}</span>
                            </div>
                          </div>
                        </div>

                        {/* Details section */}
                        <div className="p-4 space-y-3 bg-gradient-to-b from-background to-blush/10">
                          <div className="space-y-1.5">
                            <div className="flex items-center gap-2 text-muted-foreground">
                              <Briefcase className="w-3.5 h-3.5" />
                              <span className="text-sm">{candidate.occupation}</span>
                            </div>
                            <div className="flex items-center gap-2 text-muted-foreground">
                              <GraduationCap className="w-3.5 h-3.5" />
                              <span className="text-sm">{candidate.education}</span>
                            </div>
                          </div>
                          
                          {/* Match reason - highlighted */}
                          <div className="pt-2 border-t border-border/30">
                            <p className="text-xs text-rose font-medium leading-relaxed">
                              {candidate.matchReason}
                            </p>
                          </div>
                        </div>
                        
                        {/* Hover reveal action hint */}
                        <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-primary/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-center pb-3">
                          <span className="text-xs text-primary font-medium">点击查看详情</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* View all link */}
                <button 
                  className="w-full mt-4 py-3 flex items-center justify-center gap-2 text-primary text-sm font-medium rounded-xl hover:bg-rose-soft/20 transition-colors group"
                >
                  <span>查看全部推荐</span>
                  <ChevronRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Premium input area */}
      <div className="sticky bottom-24 px-5 pb-4">
        <div className="relative">
          {/* Glow effect */}
          <div className="absolute inset-0 bg-gradient-to-r from-rose-soft/30 via-gold-soft/20 to-rose-soft/30 rounded-full blur-xl opacity-50" />
          
          {/* Input container */}
          <div className="relative flex items-center gap-3 p-2 bg-card/90 backdrop-blur-xl rounded-full shadow-elevated border border-border/30">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="告诉小雅你的想法..."
              className="flex-1 px-4 py-2 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
            <button className="w-11 h-11 rounded-full bg-gradient-to-br from-primary to-rose flex items-center justify-center shadow-lg transition-all hover:shadow-xl hover:scale-105 active:scale-95">
              <Send className="w-4 h-4 text-primary-foreground" />
            </button>
          </div>
        </div>
      </div>

      {/* CSS Animation */}
      <style jsx>{`
        @keyframes fadeInUp {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  )
}
