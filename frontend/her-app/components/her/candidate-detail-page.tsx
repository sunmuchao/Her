'use client'

import { ArrowLeft, BadgeCheck, MapPin, Briefcase, GraduationCap, Heart, Sparkles, MessageCircle, AlertCircle, ChevronDown, ChevronUp, CheckCircle, Shield, ChevronLeft, ChevronRight } from 'lucide-react'
import Image from 'next/image'
import { useEffect, useState, useRef, TouchEvent } from 'react'
import type { CandidatePreview } from '@/lib/types/candidate'
import { fetchCandidateDetail } from '@/lib/api/endpoints/candidates'
import { formatExplainSourceMap } from '@/lib/api/endpoints/collected'
import { getErrorMessage } from '@/lib/api/errors'
import { canUseMockFallback } from '@/lib/mock'
import {
  DEFAULT_DEMO_CANDIDATE,
  DEMO_CANDIDATES_DATABASE,
  DEMO_VERIFIED_ITEMS,
} from '@/lib/fixtures/demo-candidates'
import { mapProfileImageUrls, PLACEHOLDER_AVATAR } from '@/lib/image-url'
import { cn } from '@/lib/utils'
import { FadeIn, Heartbeat, PageTransition } from './ui/animations'
import { ImageCarousel } from './ui/image-carousel'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
interface CandidateDetailPageProps {
  candidateId: string
  candidate?: CandidatePreview
  sessionId?: string | null
  onBack: () => void
  onStartChat: () => void
}

export default function CandidateDetailPage({
  candidateId,
  candidate,
  sessionId,
  onBack,
  onStartChat,
}: CandidateDetailPageProps) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['intro']))
  const [apiDetail, setApiDetail] = useState<{
    headline?: string
    selfIntro?: string
    images?: string[]
    matchmakerNote?: string
    matchReasons?: string[]
  } | null>(null)
  const [collectedMatchReasons, setCollectedMatchReasons] = useState<string[]>([])
  const [trustLabels, setTrustLabels] = useState<string[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const touchStartX = useRef<number | null>(null)
  const touchEndX = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setIsLoading(true)
      try {
        const data = await fetchCandidateDetail({
          candidateId,
          sessionId,
          recommendationId: candidate?.recommendationId,
        })
        if (cancelled) return
        const view = data.detail_view
        const hero = view?.hero
        const gallery =
          view?.photo_gallery
            ?.map((p) => p.url || p.image_url)
            .filter((u): u is string => Boolean(u)) || []
        setApiDetail({
          headline: hero?.headline,
          selfIntro:
            view?.self_reported_sections?.[0]?.items?.join(' ') ||
            view?.verified_sections?.[0]?.items?.join(' '),
          images: gallery.length ? gallery : undefined,
          matchmakerNote: view?.matchmaker_notes?.[0],
          matchReasons: view?.caution_sections?.[0]?.items,
        })
        setTrustLabels(data.trust_summary?.labels || [])
        if (data.explain?.source_map) {
          setCollectedMatchReasons(formatExplainSourceMap(data.explain.source_map))
        }
        setUsingMockData(false)
      } catch (error) {
        if (cancelled) return
        setLoadError(getErrorMessage(error, '资料详情加载失败'))
        if (canUseMockFallback()) setUsingMockData(true)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [candidateId, sessionId, candidate?.recommendationId])

  const rawCandidate = usingMockData
    ? (DEMO_CANDIDATES_DATABASE[candidateId] || DEFAULT_DEMO_CANDIDATE)
    : null

  const candidateData = rawCandidate
    ? {
        ...rawCandidate,
        id: candidate?.id || rawCandidate.id,
        name: candidate?.name || rawCandidate.name,
        age: candidate?.age || rawCandidate.age,
        city: candidate?.city || rawCandidate.city,
        occupation: candidate?.occupation || rawCandidate.occupation,
        education: candidate?.education || rawCandidate.education,
        verified: candidate?.verified ?? rawCandidate.verified,
        matchScore: candidate?.matchScore || rawCandidate.matchScore,
        headline:
          apiDetail?.headline ||
          candidate?.matchReason ||
          candidate?.message ||
          rawCandidate.headline,
        selfIntro:
          apiDetail?.selfIntro ||
          candidate?.message ||
          candidate?.matchReason ||
          rawCandidate.selfIntro,
        images: mapProfileImageUrls(
          apiDetail?.images ||
            (candidate?.image ? [candidate.image, ...rawCandidate.images.slice(1)] : rawCandidate.images),
        ),
        matchmakerNote: apiDetail?.matchmakerNote || rawCandidate.matchmakerNote,
        matchReasons:
          collectedMatchReasons.length
            ? collectedMatchReasons
            : apiDetail?.matchReasons || rawCandidate.matchReasons,
      }
    : {
        id: candidate?.id || candidateId,
        name: candidate?.name || '候选人',
        age: candidate?.age || 0,
        city: candidate?.city || '',
        occupation: candidate?.occupation || '',
        education: candidate?.education || '',
        height: '',
        headline: apiDetail?.headline || candidate?.matchReason || candidate?.message || '',
        verified: candidate?.verified ?? false,
        matchScore: candidate?.matchScore || 0,
        images: mapProfileImageUrls(
          apiDetail?.images || (candidate?.image ? [candidate.image] : [PLACEHOLDER_AVATAR]),
        ),
        selfIntro: apiDetail?.selfIntro || candidate?.message || candidate?.matchReason || '',
        keyPoints: [] as { label: string; value: string }[],
        needToKnow: apiDetail?.matchReasons || [],
        matchmakerNote: apiDetail?.matchmakerNote || '',
        matchReasons:
          collectedMatchReasons.length
            ? collectedMatchReasons
            : apiDetail?.matchReasons || (candidate?.matchReason ? [candidate.matchReason] : []),
      }

  if (isLoading) {
    return (
      <PageTransition className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载详情中…</p>
      </PageTransition>
    )
  }

  if (loadError && !usingMockData) {
    return (
      <PageTransition className="min-h-screen bg-background">
        <ErrorState message={loadError} onBack={onBack} />
      </PageTransition>
    )
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
    <PageTransition className="min-h-screen bg-background">
      {usingMockData && <DemoDataBanner />}
      {/* Hero Image with improved carousel */}
      <div className="relative h-[480px]">
        <ImageCarousel
          images={candidateData.images}
          alt={candidateData.name}
          aspectRatio="portrait"
          showArrows={true}
          indicatorStyle="pills"
          className="h-full"
        />
        
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/30 pointer-events-none" />
        
        {/* Back button */}
        <button
          onClick={onBack}
          className="absolute top-12 left-4 w-10 h-10 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center z-10 focus-ring transition-transform active:scale-95"
          aria-label="返回"
        >
          <ArrowLeft className="w-5 h-5 text-white" />
        </button>

        {/* Match score */}
        <div className="absolute top-12 right-4 px-3 py-1.5 bg-black/30 backdrop-blur-sm rounded-full">
          <span className="text-sm font-medium text-white">{candidateData.matchScore}% 匹配</span>
        </div>

        {/* Basic info overlay */}
        <div className="absolute bottom-0 left-0 right-0 p-5 pointer-events-none">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-3xl font-semibold text-white">{candidateData.name}</h1>
            <span className="text-xl text-white/80">{candidateData.age}</span>
            {candidateData.verified && <BadgeCheck className="w-5 h-5 text-primary" aria-label="已认证" />}
          </div>
          <p className="text-white/80 italic mb-3 text-balance">&ldquo;{candidateData.headline}&rdquo;</p>
          <div className="flex items-center gap-4 text-sm text-white/70">
            <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" aria-hidden="true" />{candidateData.city}</span>
            <span className="flex items-center gap-1"><Briefcase className="w-3.5 h-3.5" aria-hidden="true" />{candidateData.occupation}</span>
            <span className="flex items-center gap-1"><GraduationCap className="w-3.5 h-3.5" aria-hidden="true" />{candidateData.education}</span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-4 py-5 space-y-4 pb-28">
        {/* Match reasons - highlighted */}
        <FadeIn delay={100}>
          <section className="bg-primary/5 border border-primary/10 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-primary" aria-hidden="true" />
              <h3 className="font-medium text-foreground">为什么推荐给你</h3>
            </div>
            <div className="space-y-2">
              {candidateData.matchReasons.map((reason, i) => (
                <div key={i} className="flex items-start gap-2 animate-fade-in-up" style={{ animationDelay: `${i * 50}ms` }}>
                  <CheckCircle className="w-4 h-4 text-primary mt-0.5 shrink-0" aria-hidden="true" />
                  <span className="text-sm text-muted-foreground">{reason}</span>
                </div>
              ))}
            </div>
          </section>
        </FadeIn>

        {/* Verified items */}
        <FadeIn delay={200}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4 text-primary" aria-hidden="true" />
              <h3 className="font-medium">已核验信息</h3>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(trustLabels.length
                ? trustLabels.map((label) => ({ name: label, verified: true }))
                : DEMO_VERIFIED_ITEMS
              ).map((item, i) => (
                <div key={i} className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors',
                  item.verified ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground'
                )}>
                  {item.verified ? <CheckCircle className="w-4 h-4" aria-hidden="true" /> : <div className="w-4 h-4 rounded-full border-2 border-current" aria-hidden="true" />}
                  {item.name}
                </div>
              ))}
            </div>
          </section>
        </FadeIn>

        {/* Self intro - collapsible, expanded by default */}
        <FadeIn delay={300}>
          <section className="bg-card border border-border rounded-xl overflow-hidden">
            <button 
              onClick={() => toggleSection('intro')} 
              className="w-full flex items-center justify-between p-4 focus-ring"
              aria-expanded={expandedSections.has('intro')}
            >
              <h3 className="font-medium">自我介绍</h3>
              {expandedSections.has('intro') ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
            {expandedSections.has('intro') && (
              <div className="px-4 pb-4 animate-fade-in-up">
                <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{candidateData.selfIntro}</p>
              </div>
            )}
          </section>
        </FadeIn>

        {/* Key points - collapsible, collapsed by default */}
        <FadeIn delay={400}>
          <section className="bg-card border border-border rounded-xl overflow-hidden">
            <button 
              onClick={() => toggleSection('keypoints')} 
              className="w-full flex items-center justify-between p-4 focus-ring"
              aria-expanded={expandedSections.has('keypoints')}
            >
              <h3 className="font-medium">基本信息</h3>
              {expandedSections.has('keypoints') ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
            {expandedSections.has('keypoints') && (
              <div className="px-4 pb-4 animate-fade-in-up">
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
        </FadeIn>

        {/* Need to know - collapsed by default */}
        <FadeIn delay={500}>
          <section className="bg-card border border-border rounded-xl overflow-hidden">
            <button 
              onClick={() => toggleSection('needtoknow')} 
              className="w-full flex items-center justify-between p-4 focus-ring"
              aria-expanded={expandedSections.has('needtoknow')}
            >
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-gold" aria-hidden="true" />
                <h3 className="font-medium">需要了解</h3>
              </div>
              {expandedSections.has('needtoknow') ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
            {expandedSections.has('needtoknow') && (
              <div className="px-4 pb-4 space-y-2 animate-fade-in-up">
                {candidateData.needToKnow.map((item, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                    <span className="text-gold" aria-hidden="true">•</span>
                    {item}
                  </div>
                ))}
              </div>
            )}
          </section>
        </FadeIn>

        {/* Matchmaker note */}
        <FadeIn delay={600}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <MessageCircle className="w-4 h-4 text-primary" aria-hidden="true" />
              <h3 className="font-medium">红娘点评</h3>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">{candidateData.matchmakerNote}</p>
          </section>
        </FadeIn>
      </div>

      {/* Bottom CTA with heartbeat animation */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-background border-t border-border safe-area-bottom">
        <div className="flex gap-3 max-w-md mx-auto">
          <button 
            className="flex-1 py-3 border border-border rounded-xl text-foreground font-medium hover:bg-secondary transition-colors focus-ring"
            aria-label="暂时跳过这位候选人"
          >
            暂时跳过
          </button>
          <Heartbeat>
            <button 
              onClick={onStartChat} 
              className="flex-1 py-3 bg-primary rounded-xl text-primary-foreground font-medium flex items-center justify-center gap-2 hover:bg-primary/90 transition-all focus-ring shadow-lg shadow-primary/20"
              aria-label={`开始和${candidateData.name}聊天`}
            >
              <Heart className="w-4 h-4" aria-hidden="true" />
              开始聊天
            </button>
          </Heartbeat>
        </div>
      </div>
    </PageTransition>
  )
}
