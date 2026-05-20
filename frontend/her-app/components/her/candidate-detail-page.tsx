'use client'

import { ArrowLeft, BadgeCheck, MapPin, Briefcase, GraduationCap, Heart, Sparkles, MessageCircle, AlertCircle, ChevronDown, ChevronUp, CheckCircle, Shield, ChevronLeft, ChevronRight } from 'lucide-react'
import Image from 'next/image'
import { useState, useEffect, useRef, TouchEvent } from 'react'
import type { CandidatePreview } from '@/lib/her-types'

interface CandidateDetailPageProps {
  candidateId: string
  candidate?: CandidatePreview
  onBack: () => void
  onStartChat: () => void
}

// Candidate data
const candidatesDatabase: Record<string, {
  id: string
  name: string
  age: number
  city: string
  occupation: string
  education: string
  height: string
  headline: string
  verified: boolean
  matchScore: number
  images: string[]
  selfIntro: string
  keyPoints: { label: string; value: string }[]
  needToKnow: string[]
  matchmakerNote: string
  matchReasons: string[]
}> = {
  '1': {
    id: '1',
    name: '林悦',
    age: 28,
    city: '上海',
    occupation: '产品设计师',
    education: '复旦大学',
    height: '165cm',
    headline: '相信设计改变生活',
    verified: true,
    matchScore: 95,
    images: [
      'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '热爱设计，相信美好的事物能改变生活。工作之余喜欢探索城市里的小店，记录生活中的美好瞬间。',
    keyPoints: [
      { label: '作息', value: '早睡早起型' },
      { label: '饮食', value: '偏清淡' },
      { label: '运动', value: '瑜伽、游泳' },
      { label: '宠物', value: '养了一只猫' },
    ],
    needToKnow: ['她比较注重隐私，初次见面建议选择公共场所', '她有一只猫，如果你对猫过敏需要考虑'],
    matchmakerNote: '林悦是一个温和细腻的女生，对感情认真负责。建议你们可以从共同的兴趣爱好聊起。',
    matchReasons: ['你们都在上海，距离很近', '她的性格温柔，符合你的期待', '审美品味相近'],
  },
  '2': {
    id: '2',
    name: '陈思',
    age: 27,
    city: '上海',
    occupation: '品牌策划',
    education: '浙江大学',
    height: '168cm',
    headline: '在创意中寻找生活的无限可能',
    verified: true,
    matchScore: 92,
    images: [
      'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1502823403499-6ccfcf4fb453?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '热爱创意工作，喜欢用故事打动人心。周末常常泡在书店或者去看话剧。',
    keyPoints: [
      { label: '作息', value: '夜猫子型' },
      { label: '饮食', value: '美食爱好者' },
      { label: '运动', value: '跑步、网球' },
      { label: '宠物', value: '暂时没有' },
    ],
    needToKnow: ['她工作较忙，可能回复消息不及时', '她比较独立，需要个人空间'],
    matchmakerNote: '陈思是一个非常有想法的女生，事业心比较强但也渴望爱情。建议从旅行或阅读的话题聊起。',
    matchReasons: ['价值观相似，追求品质生活', '兴趣爱好有交集', '都有独立的人格'],
  },
  '3': {
    id: '3',
    name: '王晴',
    age: 26,
    city: '杭州',
    occupation: '插画师',
    education: '中国美院',
    height: '162cm',
    headline: '用画笔记录世界的美好',
    verified: true,
    matchScore: 88,
    images: [
      'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1502767089025-6572583495f9?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '自由插画师，用画笔讲故事。喜欢安静的生活，经常在西湖边写生。',
    keyPoints: [
      { label: '作息', value: '自由作息' },
      { label: '饮食', value: '素食为主' },
      { label: '运动', value: '散步、骑行' },
      { label: '宠物', value: '两只猫' },
    ],
    needToKnow: ['她在杭州，可能需要异地', '她是自由职业，收入不太稳定'],
    matchmakerNote: '王晴是一个非常有艺术气息的女生，性格温和，向往简单纯粹的生活。',
    matchReasons: ['艺术气质契合', '生活态度相似', '都向往简单纯粹的感情'],
  },
  '4': {
    id: '4',
    name: '张雨',
    age: 29,
    city: '北京',
    occupation: '建筑师',
    education: '清华大学',
    height: '170cm',
    headline: '在理性与浪漫之间寻找平衡',
    verified: true,
    matchScore: 85,
    images: [
      'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800&h=1200&fit=crop&crop=face',
      'https://images.unsplash.com/photo-1488426862026-3ee34a7d66df?w=800&h=1200&fit=crop&crop=face',
    ],
    selfIntro: '建筑师，喜欢创造有温度的空间。工作之余喜欢研究咖啡和红酒。',
    keyPoints: [
      { label: '作息', value: '规律作息' },
      { label: '饮食', value: '健康饮食' },
      { label: '运动', value: '健身、普拉提' },
      { label: '宠物', value: '暂时没有' },
    ],
    needToKnow: ['她在北京，需要异地', '她对另一半要求较高'],
    matchmakerNote: '张雨是一个非常优秀的女生，事业有成但也渴望稳定的感情。',
    matchReasons: ['对未来家庭有清晰规划', '追求高品质生活', '价值观一致'],
  },
}

const defaultCandidate = candidatesDatabase['1']

const verifiedItems = [
  { name: '身份信息', verified: true },
  { name: '学历认证', verified: true },
  { name: '职业信息', verified: true },
  { name: '收入水平', verified: false },
]

export default function CandidateDetailPage({ candidateId, candidate, onBack, onStartChat }: CandidateDetailPageProps) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['intro']))
  const touchStartX = useRef<number | null>(null)
  const touchEndX = useRef<number | null>(null)

  const rawCandidate = candidatesDatabase[candidateId] || defaultCandidate
  const candidateData = {
    ...rawCandidate,
    id: candidate?.id || rawCandidate.id,
    name: candidate?.name || rawCandidate.name,
    age: candidate?.age || rawCandidate.age,
    city: candidate?.city || rawCandidate.city,
    occupation: candidate?.occupation || rawCandidate.occupation,
    education: candidate?.education || rawCandidate.education,
    verified: candidate?.verified ?? rawCandidate.verified,
    matchScore: candidate?.matchScore || rawCandidate.matchScore,
    headline: candidate?.matchReason || candidate?.message || rawCandidate.headline,
    selfIntro: candidate?.message || candidate?.matchReason || rawCandidate.selfIntro,
    images: candidate?.image ? [candidate.image, ...rawCandidate.images.slice(1)] : rawCandidate.images,
  }

  const handleTouchStart = (e: TouchEvent) => { touchStartX.current = e.touches[0].clientX }
  const handleTouchMove = (e: TouchEvent) => { touchEndX.current = e.touches[0].clientX }
  const handleTouchEnd = () => {
    if (!touchStartX.current || !touchEndX.current) return
    const diff = touchStartX.current - touchEndX.current
    if (Math.abs(diff) > 50) {
      if (diff > 0 && currentImageIndex < candidateData.images.length - 1) {
        setCurrentImageIndex(prev => prev + 1)
      } else if (diff < 0 && currentImageIndex > 0) {
        setCurrentImageIndex(prev => prev - 1)
      }
    }
    touchStartX.current = null
    touchEndX.current = null
  }

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Hero Image */}
      <div 
        className="relative h-[480px]"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <Image
          src={candidateData.images[currentImageIndex]}
          alt={candidateData.name}
          fill
          className="object-cover"
          priority
        />
        
        {/* Gradient overlay - simple */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/30" />
        
        {/* Back button */}
        <button
          onClick={onBack}
          className="absolute top-12 left-4 w-10 h-10 rounded-full bg-black/30 flex items-center justify-center z-10"
        >
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>

        {/* Match score */}
        <div className="absolute top-12 right-4 px-3 py-1.5 bg-black/30 rounded-full">
          <span className="text-sm font-medium text-white">{candidateData.matchScore}% 匹配</span>
        </div>

        {/* Image pagination */}
        {candidateData.images.length > 1 && (
          <>
            <div className="absolute top-12 left-1/2 -translate-x-1/2 px-2 py-1 bg-black/30 rounded-full">
              <span className="text-xs text-white">{currentImageIndex + 1}/{candidateData.images.length}</span>
            </div>
            <div className="absolute bottom-32 left-1/2 -translate-x-1/2 flex gap-1.5">
              {candidateData.images.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrentImageIndex(i)}
                  className={`h-1 rounded-full transition-all ${i === currentImageIndex ? 'bg-white w-6' : 'bg-white/50 w-3'}`}
                />
              ))}
            </div>
            {currentImageIndex > 0 && (
              <button onClick={() => setCurrentImageIndex(i => i - 1)} className="absolute left-3 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/30 flex items-center justify-center">
                <ChevronLeft className="w-4 h-4 text-white" />
              </button>
            )}
            {currentImageIndex < candidateData.images.length - 1 && (
              <button onClick={() => setCurrentImageIndex(i => i + 1)} className="absolute right-3 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/30 flex items-center justify-center">
                <ChevronRight className="w-4 h-4 text-white" />
              </button>
            )}
          </>
        )}

        {/* Basic info overlay */}
        <div className="absolute bottom-0 left-0 right-0 p-5">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-3xl font-semibold text-white">{candidateData.name}</h1>
            <span className="text-xl text-white/80">{candidateData.age}</span>
            {candidateData.verified && <BadgeCheck className="w-5 h-5 text-primary" />}
          </div>
          <p className="text-white/80 italic mb-3">&ldquo;{candidateData.headline}&rdquo;</p>
          <div className="flex items-center gap-4 text-sm text-white/70">
            <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />{candidateData.city}</span>
            <span className="flex items-center gap-1"><Briefcase className="w-3.5 h-3.5" />{candidateData.occupation}</span>
            <span className="flex items-center gap-1"><GraduationCap className="w-3.5 h-3.5" />{candidateData.education}</span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-4 py-5 space-y-4 pb-28">
        {/* Match reasons - highlighted */}
        <section className="bg-primary/5 border border-primary/10 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-primary" />
            <h3 className="font-medium text-foreground">为什么推荐给你</h3>
          </div>
          <div className="space-y-2">
            {candidateData.matchReasons.map((reason, i) => (
              <div key={i} className="flex items-start gap-2">
                <CheckCircle className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span className="text-sm text-muted-foreground">{reason}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Verified items */}
        <section className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-primary" />
            <h3 className="font-medium">已核验信息</h3>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {verifiedItems.map((item, i) => (
              <div key={i} className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${
                item.verified ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground'
              }`}>
                {item.verified ? <CheckCircle className="w-4 h-4" /> : <div className="w-4 h-4 rounded-full border-2 border-current" />}
                {item.name}
              </div>
            ))}
          </div>
        </section>

        {/* Self intro - collapsible */}
        <section className="bg-card border border-border rounded-xl overflow-hidden">
          <button onClick={() => toggleSection('intro')} className="w-full flex items-center justify-between p-4">
            <h3 className="font-medium">自我介绍</h3>
            {expandedSections.has('intro') ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
          </button>
          {expandedSections.has('intro') && (
            <div className="px-4 pb-4">
              <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{candidateData.selfIntro}</p>
            </div>
          )}
        </section>

        {/* Key points - collapsible */}
        <section className="bg-card border border-border rounded-xl overflow-hidden">
          <button onClick={() => toggleSection('keypoints')} className="w-full flex items-center justify-between p-4">
            <h3 className="font-medium">基本信息</h3>
            {expandedSections.has('keypoints') ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
          </button>
          {expandedSections.has('keypoints') && (
            <div className="px-4 pb-4">
              <div className="grid grid-cols-2 gap-3">
                {candidateData.keyPoints.map((point, i) => (
                  <div key={i} className="flex flex-col">
                    <span className="text-xs text-muted-foreground">{point.label}</span>
                    <span className="text-sm">{point.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Need to know */}
        <section className="bg-card border border-border rounded-xl overflow-hidden">
          <button onClick={() => toggleSection('needtoknow')} className="w-full flex items-center justify-between p-4">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-gold" />
              <h3 className="font-medium">需要了解</h3>
            </div>
            {expandedSections.has('needtoknow') ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
          </button>
          {expandedSections.has('needtoknow') && (
            <div className="px-4 pb-4 space-y-2">
              {candidateData.needToKnow.map((item, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                  <span className="text-gold">•</span>
                  {item}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Matchmaker note */}
        <section className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <MessageCircle className="w-4 h-4 text-primary" />
            <h3 className="font-medium">红娘点评</h3>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed">{candidateData.matchmakerNote}</p>
        </section>
      </div>

      {/* Bottom CTA - simple */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-background border-t border-border safe-area-bottom">
        <div className="flex gap-3 max-w-md mx-auto">
          <button className="flex-1 py-3 border border-border rounded-xl text-foreground font-medium hover:bg-secondary transition-colors">
            暂时跳过
          </button>
          <button onClick={onStartChat} className="flex-1 py-3 bg-primary rounded-xl text-primary-foreground font-medium flex items-center justify-center gap-2 hover:bg-primary/90 transition-colors">
            <Heart className="w-4 h-4" />
            开始聊天
          </button>
        </div>
      </div>
    </div>
  )
}
