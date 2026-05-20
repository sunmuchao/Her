'use client'

import { ArrowLeft, BadgeCheck, MapPin, Briefcase, GraduationCap, Heart, Sparkles, MessageCircle, AlertCircle, ChevronDown, ChevronUp, CheckCircle, Info, Star, Shield, Coffee, Camera, Music } from 'lucide-react'
import Image from 'next/image'
import { useState, useEffect } from 'react'

interface CandidateDetailPageProps {
  candidateId: string
  onBack: () => void
  onStartChat: (chatId: string) => void
}

const candidateData = {
  id: '1',
  name: '林悦',
  age: 28,
  city: '上海',
  district: '静安区',
  occupation: '产品设计师',
  company: '某知名互联网公司',
  education: '复旦大学',
  degree: '本科',
  major: '视觉传达设计',
  height: '165cm',
  headline: '相信设计改变生活',
  verified: true,
  matchScore: 95,
  personality: '温柔细腻',
  zodiac: '天秤座',
  mbti: 'INFJ',
  images: [
    'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=800&h=1200&fit=crop&crop=face',
    'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=800&h=1200&fit=crop&crop=face',
    'https://images.unsplash.com/photo-1517841905240-472988babdf9?w=800&h=1200&fit=crop&crop=face',
  ],
  verifiedItems: [
    { name: '身份信息', verified: true, icon: Shield },
    { name: '学历认证', verified: true, icon: GraduationCap },
    { name: '职业信息', verified: true, icon: Briefcase },
    { name: '收入水平', verified: false, icon: Star },
  ],
  selfIntro: '热爱设计，相信美好的事物能改变生活。\n\n工作之余喜欢探索城市里的小店，记录生活中的美好瞬间。周末经常会去看展览或者找一家安静的咖啡店发呆。\n\n希望能遇到一个有趣的灵魂，一起感受生活的美好。',
  interests: [
    { name: '咖啡', icon: Coffee },
    { name: '摄影', icon: Camera },
    { name: '音乐', icon: Music },
  ],
  keyPoints: [
    { label: '作息', value: '早睡早起型', emoji: '🌅' },
    { label: '饮食', value: '偏清淡，偶尔喝酒', emoji: '🥗' },
    { label: '运动', value: '瑜伽、游泳', emoji: '🧘‍♀️' },
    { label: '兴趣', value: '摄影、看展、咖啡', emoji: '📷' },
    { label: '宠物', value: '养了一只猫', emoji: '🐱' },
    { label: '婚姻观', value: '期待稳定的婚姻关系', emoji: '💍' },
  ],
  needToKnow: [
    '她比较注重隐私，初次见面建议选择公共场所',
    '她有一只猫，如果你对猫过敏需要考虑',
  ],
  suggestConfirm: [
    '关于未来定居城市的想法',
    '对家庭分工的期待',
  ],
  matchmakerNote: '林悦是一个温和细腻的女生，对感情认真负责。她的审美品味很好，对生活品质有一定追求。建议你们可以从共同的兴趣爱好聊起，她对设计和艺术领域很有见解。',
  matchReasons: [
    '你们都在上海，距离很近',
    '她的性格温柔，符合你的期待',
    '你们的审美品味相近',
    '生活作息比较一致',
  ],
}

export default function CandidateDetailPage({ candidateId, onBack, onStartChat }: CandidateDetailPageProps) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['intro', 'keypoints']))
  const [heroLoaded, setHeroLoaded] = useState(false)

  useEffect(() => {
    setHeroLoaded(true)
  }, [])

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(section)) {
        next.delete(section)
      } else {
        next.add(section)
      }
      return next
    })
  }

  return (
    <div className="min-h-screen bg-background max-w-md mx-auto">
      {/* CINEMATIC HERO SECTION - Magazine Cover Style */}
      <div className="relative">
        {/* Full-bleed image gallery */}
        <div className="relative h-[600px] overflow-hidden">
          {/* Main image with cinematic treatment */}
          <div className="absolute inset-0">
            <Image
              src={candidateData.images[currentImageIndex]}
              alt={candidateData.name}
              fill
              className={`object-cover transition-all duration-1000 ${
                heroLoaded ? 'scale-100 opacity-100' : 'scale-105 opacity-0'
              }`}
              priority
            />
          </div>
          
          {/* Cinematic gradient layers */}
          <div className="absolute inset-0 bg-gradient-to-t from-[#1a1714] via-[#1a1714]/30 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-br from-rose/5 via-transparent to-gold/5" />
          
          {/* Vignette effect */}
          <div 
            className="absolute inset-0"
            style={{
              background: 'radial-gradient(ellipse at center, transparent 50%, rgba(26,23,20,0.3) 100%)'
            }}
          />
          
          {/* Top navigation overlay */}
          <div className="absolute top-0 inset-x-0 h-32 bg-gradient-to-b from-foreground/40 to-transparent" />
          
          {/* Back button - premium glass style */}
          <button
            onClick={onBack}
            className={`absolute top-12 left-5 w-11 h-11 rounded-full bg-background/20 backdrop-blur-xl flex items-center justify-center shadow-lg z-10 border border-white/10 transition-all duration-500 hover:bg-background/30 ${
              heroLoaded ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-4'
            }`}
          >
            <ArrowLeft className="w-5 h-5 text-white" />
          </button>

          {/* Match score - editorial badge */}
          <div 
            className={`absolute top-12 right-5 transition-all duration-700 delay-200 ${
              heroLoaded ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'
            }`}
          >
            <div className="relative group">
              <div className="absolute inset-0 bg-gold/40 rounded-full blur-lg group-hover:blur-xl transition-all" />
              <div className="relative px-4 py-2 bg-gradient-to-r from-[#c8a888] via-[#d4b89a] to-[#c8a888] rounded-full flex items-center gap-2 shadow-xl">
                <Sparkles className="w-4 h-4 text-[#1a1714]" />
                <span className="text-sm font-bold text-[#1a1714]">{candidateData.matchScore}% 匹配</span>
              </div>
            </div>
          </div>

          {/* Image pagination - minimal elegant dots */}
          <div 
            className={`absolute bottom-48 left-1/2 -translate-x-1/2 flex gap-3 transition-all duration-700 delay-300 ${
              heroLoaded ? 'opacity-100' : 'opacity-0'
            }`}
          >
            {candidateData.images.map((_, index) => (
              <button
                key={index}
                onClick={() => setCurrentImageIndex(index)}
                className={`h-1 rounded-full transition-all duration-300 ${
                  index === currentImageIndex 
                    ? 'bg-white w-8' 
                    : 'bg-white/40 w-4 hover:bg-white/60'
                }`}
              />
            ))}
          </div>

          {/* EDITORIAL HERO INFO - Magazine style typography */}
          <div 
            className={`absolute bottom-0 left-0 right-0 p-6 pb-8 transition-all duration-1000 delay-100 ${
              heroLoaded ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
            }`}
          >
            {/* Personality tag */}
            <div className="flex items-center gap-2 mb-3">
              <span className="px-3 py-1 bg-white/15 backdrop-blur-md rounded-full text-xs text-white/90 font-medium border border-white/10">
                {candidateData.personality}
              </span>
              <span className="px-3 py-1 bg-white/15 backdrop-blur-md rounded-full text-xs text-white/90 font-medium border border-white/10">
                {candidateData.mbti}
              </span>
            </div>
            
            {/* Name - editorial typography */}
            <div className="flex items-baseline gap-3 mb-2">
              <h1 
                className="editorial-title text-5xl text-white tracking-tight"
                style={{ textShadow: '0 4px 30px rgba(0,0,0,0.5)' }}
              >
                {candidateData.name}
              </h1>
              <span className="text-2xl text-white/70 font-light">{candidateData.age}</span>
              {candidateData.verified && (
                <BadgeCheck className="w-7 h-7 text-gold" />
              )}
            </div>
            
            {/* Headline - italic editorial style */}
            <p 
              className="text-lg text-white/80 italic mb-4 font-serif"
              style={{ textShadow: '0 2px 20px rgba(0,0,0,0.4)' }}
            >
              &ldquo;{candidateData.headline}&rdquo;
            </p>
            
            {/* Location and profession - refined layout */}
            <div className="flex flex-wrap items-center gap-3 text-white/70">
              <span className="flex items-center gap-1.5 text-sm">
                <MapPin className="w-4 h-4" />
                {candidateData.city} · {candidateData.district}
              </span>
              <span className="w-1 h-1 rounded-full bg-white/40" />
              <span className="flex items-center gap-1.5 text-sm">
                <Briefcase className="w-4 h-4" />
                {candidateData.occupation}
              </span>
              <span className="w-1 h-1 rounded-full bg-white/40" />
              <span className="flex items-center gap-1.5 text-sm">
                <GraduationCap className="w-4 h-4" />
                {candidateData.education}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Content sections with premium styling */}
      <div className="px-5 py-6 space-y-5 pb-36 bg-gradient-to-b from-background via-background to-blush/10">
        
        {/* Match reasons - WHY this match card */}
        <section 
          className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-rose-soft/40 via-blush/30 to-gold-soft/20 p-5 shadow-soft"
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-gold-soft/30 to-transparent rounded-bl-full" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold to-[#d4b89a] flex items-center justify-center shadow-md">
                <Sparkles className="w-4 h-4 text-[#1a1714]" />
              </div>
              <h3 className="font-semibold text-foreground">为什么推荐给你</h3>
            </div>
            <div className="space-y-2">
              {candidateData.matchReasons.map((reason, index) => (
                <div key={index} className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                  <span className="text-sm text-taupe">{reason}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Verified items - Premium verification display */}
        <section className="bg-card rounded-2xl p-5 shadow-soft border border-border/30">
          <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" />
            平台已核验
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {candidateData.verifiedItems.map((item, index) => {
              const IconComponent = item.icon
              return (
                <div
                  key={index}
                  className={`flex items-center gap-2.5 p-3 rounded-xl transition-all ${
                    item.verified 
                      ? 'bg-green-50 border border-green-200' 
                      : 'bg-secondary/50 border border-border/30'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    item.verified ? 'bg-green-100' : 'bg-secondary'
                  }`}>
                    <IconComponent className={`w-4 h-4 ${
                      item.verified ? 'text-green-600' : 'text-muted-foreground'
                    }`} />
                  </div>
                  <div>
                    <span className={`text-sm font-medium ${
                      item.verified ? 'text-green-700' : 'text-muted-foreground'
                    }`}>
                      {item.name}
                    </span>
                    {item.verified && (
                      <span className="text-[10px] text-green-600 block">已验证</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* Basic info card */}
        <section className="bg-card rounded-2xl p-5 shadow-soft border border-border/30">
          <h3 className="text-sm font-semibold text-foreground mb-4">基本信息</h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-3 bg-blush/30 rounded-xl">
              <span className="text-xs text-muted-foreground block mb-1">身高</span>
              <span className="text-sm font-medium text-foreground">{candidateData.height}</span>
            </div>
            <div className="text-center p-3 bg-blush/30 rounded-xl">
              <span className="text-xs text-muted-foreground block mb-1">星座</span>
              <span className="text-sm font-medium text-foreground">{candidateData.zodiac}</span>
            </div>
            <div className="text-center p-3 bg-blush/30 rounded-xl">
              <span className="text-xs text-muted-foreground block mb-1">MBTI</span>
              <span className="text-sm font-medium text-foreground">{candidateData.mbti}</span>
            </div>
          </div>
        </section>

        {/* Self introduction - Elegant expandable */}
        <section className="bg-card rounded-2xl shadow-soft border border-border/30 overflow-hidden">
          <button
            onClick={() => toggleSection('intro')}
            className="w-full px-5 py-4 flex items-center justify-between text-left"
          >
            <h3 className="text-sm font-semibold text-foreground">关于我</h3>
            {expandedSections.has('intro') ? (
              <ChevronUp className="w-5 h-5 text-muted-foreground" />
            ) : (
              <ChevronDown className="w-5 h-5 text-muted-foreground" />
            )}
          </button>
          {expandedSections.has('intro') && (
            <div className="px-5 pb-5">
              <p className="text-sm text-taupe leading-relaxed whitespace-pre-line italic font-serif">
                {candidateData.selfIntro}
              </p>
            </div>
          )}
        </section>

        {/* Key points - Visual grid */}
        <section className="bg-card rounded-2xl shadow-soft border border-border/30 overflow-hidden">
          <button
            onClick={() => toggleSection('keypoints')}
            className="w-full px-5 py-4 flex items-center justify-between text-left"
          >
            <h3 className="text-sm font-semibold text-foreground">生活方式</h3>
            {expandedSections.has('keypoints') ? (
              <ChevronUp className="w-5 h-5 text-muted-foreground" />
            ) : (
              <ChevronDown className="w-5 h-5 text-muted-foreground" />
            )}
          </button>
          {expandedSections.has('keypoints') && (
            <div className="px-5 pb-5">
              <div className="grid grid-cols-2 gap-3">
                {candidateData.keyPoints.map((point, index) => (
                  <div key={index} className="bg-gradient-to-br from-blush/40 to-rose-soft/20 rounded-xl p-3.5 border border-rose-soft/20">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base">{point.emoji}</span>
                      <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wide">{point.label}</span>
                    </div>
                    <p className="text-sm text-foreground font-medium">{point.value}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Need to know - Warm attention card */}
        <section className="bg-gradient-to-br from-rose-soft/50 to-blush/40 rounded-2xl p-5 border border-rose/20">
          <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <Info className="w-4 h-4 text-rose" />
            你需要知道
          </h3>
          <ul className="space-y-3">
            {candidateData.needToKnow.map((item, index) => (
              <li key={index} className="text-sm text-taupe flex items-start gap-3">
                <span className="w-1.5 h-1.5 rounded-full bg-rose mt-2 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </section>

        {/* Suggest confirm - Golden attention card */}
        <section className="bg-gradient-to-br from-gold-soft/50 to-blush/30 rounded-2xl p-5 border border-gold/20">
          <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-gold" />
            建议先确认
          </h3>
          <ul className="space-y-3">
            {candidateData.suggestConfirm.map((item, index) => (
              <li key={index} className="text-sm text-taupe flex items-start gap-3">
                <span className="w-1.5 h-1.5 rounded-full bg-gold mt-2 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </section>

        {/* Matchmaker note - Premium editorial style */}
        <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-card via-blush/20 to-rose-soft/30 p-5 shadow-elevated border border-rose-soft/30">
          <div className="absolute -top-8 -right-8 w-32 h-32 bg-gradient-to-bl from-gold-soft/30 to-transparent rounded-full blur-2xl" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold to-[#d4b89a] flex items-center justify-center shadow-md">
                <Sparkles className="w-4 h-4 text-[#1a1714]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">红娘小雅的话</h3>
                <span className="text-[10px] text-muted-foreground">专属推荐建议</span>
              </div>
            </div>
            <p className="text-sm text-taupe leading-relaxed italic">
              &ldquo;{candidateData.matchmakerNote}&rdquo;
            </p>
          </div>
        </section>
      </div>

      {/* PREMIUM Fixed bottom CTA */}
      <div className="fixed bottom-0 left-0 right-0 max-w-md mx-auto safe-area-bottom">
        <div className="relative">
          {/* Blur backdrop */}
          <div className="absolute inset-0 bg-background/80 backdrop-blur-xl" />
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/90 to-transparent" />
          
          {/* Content */}
          <div className="relative p-5 pt-4">
            <div className="flex gap-3">
              <button className="flex-1 py-4 bg-secondary hover:bg-secondary/80 rounded-2xl text-foreground font-medium text-sm transition-all active:scale-[0.98] border border-border/30">
                <Heart className="w-4 h-4 inline mr-2" />
                先保存
              </button>
              <button 
                onClick={() => onStartChat(candidateData.id)}
                className="flex-2 flex-[1.5] py-4 bg-gradient-to-r from-primary via-rose to-primary rounded-2xl text-primary-foreground font-medium text-sm shadow-lg hover:shadow-xl transition-all active:scale-[0.98] flex items-center justify-center gap-2"
              >
                <MessageCircle className="w-4 h-4" />
                开始聊天
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
