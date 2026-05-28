'use client'

import { ArrowLeft, BadgeCheck, MapPin, Briefcase, GraduationCap, Heart, Sparkles, MessageCircle, AlertCircle, ChevronDown, ChevronUp, CheckCircle, Shield } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import { expressDiscoveryCandidateInterest } from '@/lib/api/endpoints/discovery'
import { createProxyIntroRequest, replyProxyIntroCase } from '@/lib/api/endpoints/proxy-intro'
import { fetchMyProxyIntroCases } from '@/lib/api/endpoints/proxy-intro'
import { notifyError } from '@/lib/notify'

interface CandidateDetailPageProps {
  candidateId: string
  candidate?: CandidatePreview
  sessionId?: string | null
  onBack: () => void
  onOpenRelationships: () => void
  // 新增：被动推荐场景需要的参数
  caseId?: string // 案件 ID（被动推荐场景）
  viewType?: 'delayed' | 'matched' | 'interest' | 'candidate' // 卡片类型，interest 表示被动推荐
}

export default function CandidateDetailPage({
  candidateId,
  candidate,
  sessionId,
  onBack,
  onOpenRelationships,
  caseId,
  viewType,
}: CandidateDetailPageProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['intro']))

  // DEBUG: 调试参数传递
  useEffect(() => {
    console.log('[CandidateDetailPage] 接收到的参数:', {
      candidateId,
      candidate: candidate ? {
        id: candidate.id,
        caseId: candidate.caseId,
        viewType: candidate.viewType,
        subscriptionId: candidate.subscriptionId,
      } : null,
      sessionId,
      caseId_prop: caseId,
      viewType_prop: viewType,
    })
  }, [candidateId, candidate, sessionId, caseId, viewType])
  const [apiDetail, setApiDetail] = useState<{
    headline?: string
    selfIntro?: string
    images?: string[]
    matchmakerNote?: string
    matchReasons?: string[]
  } | null>(null)
  const [profileFacts, setProfileFacts] = useState<Record<string, unknown>>({})
  const [collectedMatchReasons, setCollectedMatchReasons] = useState<string[]>([])
  const [trustLabels, setTrustLabels] = useState<string[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isExpressingInterest, setIsExpressingInterest] = useState(false)
  const [showSubmittedHint, setShowSubmittedHint] = useState(false)

  function formatHeight(value: unknown): string {
    const num = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(num) && num > 0 ? `${num}cm` : ''
  }

  function formatIncome(value: unknown): string {
    if (value == null || value === '') return ''
    return String(value)
  }

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
        const facts = data.profile_facts || {}
        const hero = view?.hero
        const gallery =
          view?.photo_gallery
            ?.map((p) => p.url || p.image_url)
            .filter((u): u is string => Boolean(u)) || []
        setProfileFacts(facts)
        setApiDetail({
          headline: hero?.headline,
          selfIntro:
            view?.self_reported_sections?.[0]?.items?.join(' ') ||
            view?.verified_sections?.[0]?.items?.join(' ') ||
            String(facts.public_notes || facts.public_personality || ''),
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
  const recommendationTargetId = candidate?.recommendationId
  const subscriptionId = candidate?.subscriptionId
  const resolvedCandidateId = candidate?.id || candidateId
  // 主动发起场景：需要有 candidateId 和 subscriptionId/sessionId
  // 被动推荐场景：只需要有 caseId
  const canExpressInterest = viewType === 'interest' && caseId
    ? Boolean(caseId)
    : Boolean(resolvedCandidateId && (subscriptionId || sessionId))

  // DEBUG: 调试按钮状态
  console.log('[CandidateDetailPage] canExpressInterest 计算:', {
    viewType,
    caseId,
    resolvedCandidateId,
    subscriptionId,
    sessionId,
    result: canExpressInterest,
    condition_check: {
      is_interest_type: viewType === 'interest',
      has_caseId: Boolean(caseId),
      first_branch: viewType === 'interest' && caseId ? Boolean(caseId) : 'N/A',
      second_branch: Boolean(resolvedCandidateId && (subscriptionId || sessionId)),
    },
  })

  // 处理"暂不考虑"（被动推荐场景）
  const handleDecline = async () => {
    if (isExpressingInterest) return
    if (viewType !== 'interest' || !caseId) return

    setIsExpressingInterest(true)
    try {
      await replyProxyIntroCase({
        caseId,
        replyType: 'declined',
        source: 'candidate_detail_reply',
      })
      // 返回上一页
      onBack()
    } catch (error) {
      notifyError(error, '暂不考虑失败，请稍后重试')
    } finally {
      setIsExpressingInterest(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    const numericCandidateId = Number(resolvedCandidateId)
    if (!Number.isFinite(numericCandidateId) || numericCandidateId <= 0) {
      setShowSubmittedHint(false)
      return
    }

    async function loadSubmittedState() {
      try {
        const response = await fetchMyProxyIntroCases()
        if (cancelled) return
        const hasExistingCase = (response.cases || []).some(
          (item) =>
            item.role === 'requester' &&
            Number(item.counterpart_profile_id || 0) === numericCandidateId,
        )
        setShowSubmittedHint(hasExistingCase)
      } catch {
        if (!cancelled) setShowSubmittedHint(false)
      }
    }

    void loadSubmittedState()
    return () => {
      cancelled = true
    }
  }, [resolvedCandidateId])

  const factImages = mapProfileImageUrls(
    [profileFacts.avatar_url, profileFacts.photo_url, profileFacts.cover_url].filter(Boolean).map(String),
  )
  const factName = String(profileFacts.display_name || profileFacts.name || candidate?.name || '候选人')
  const factHeadline = String(
    profileFacts.public_notes ||
      profileFacts.public_personality ||
      profileFacts.relationship_goal ||
      candidate?.matchReason ||
      candidate?.message ||
      '',
  )
  const factSelfIntro = String(
    profileFacts.public_notes ||
      profileFacts.public_personality ||
      profileFacts.public_values ||
      profileFacts.public_job ||
      '',
  )
  const factKeyPoints = [
    profileFacts.city ? { label: '城市', value: String(profileFacts.city) } : null,
    profileFacts.age ? { label: '年龄', value: String(profileFacts.age) } : null,
    profileFacts.job ? { label: '职业', value: String(profileFacts.job) } : null,
    profileFacts.education ? { label: '学历', value: String(profileFacts.education) } : null,
    profileFacts.relationship_goal ? { label: '关系目标', value: String(profileFacts.relationship_goal) } : null,
    profileFacts.marital_status ? { label: '婚况', value: String(profileFacts.marital_status) } : null,
    formatHeight(profileFacts.height) ? { label: '身高', value: formatHeight(profileFacts.height) } : null,
    profileFacts.income_range ? { label: '收入', value: formatIncome(profileFacts.income_range) } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item))

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
        name: factName,
        age: candidate?.age || (typeof profileFacts.age === 'number' ? profileFacts.age : 0),
        city: candidate?.city || String(profileFacts.city || ''),
        occupation: candidate?.occupation || String(profileFacts.job || ''),
        education: candidate?.education || String(profileFacts.education || ''),
        height: '',
        headline: apiDetail?.headline || factHeadline,
        verified: candidate?.verified ?? Boolean(profileFacts.verified || profileFacts.live_video_verified),
        matchScore: candidate?.matchScore || 0,
        images: mapProfileImageUrls(
          apiDetail?.images || factImages || (candidate?.image ? [candidate.image] : [PLACEHOLDER_AVATAR]),
        ),
        selfIntro: apiDetail?.selfIntro || factSelfIntro || candidate?.message || candidate?.matchReason || '',
        keyPoints: factKeyPoints,
        needToKnow: apiDetail?.matchReasons || [],
        matchmakerNote: apiDetail?.matchmakerNote || String(profileFacts.public_notes || ''),
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

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  const handleExpressInterest = async () => {
    if (isExpressingInterest) return

    // 场景1：被动推荐（有人想认识你）→ 点击愿意认识 = 回复案件
    if (viewType === 'interest' && caseId) {
      setIsExpressingInterest(true)
      try {
        await replyProxyIntroCase({
          caseId,
          replyType: 'accepted',
          source: 'candidate_detail_reply',
        })
        setShowSubmittedHint(true)
      } catch (error) {
        notifyError(error, '接受失败，请稍后重试')
      } finally {
        setIsExpressingInterest(false)
      }
      return
    }

    // 场景2：主动发起认识请求
    if (!candidateData.id) {
      notifyError(new Error('interest_unavailable'), '当前候选人暂时无法发起认识')
      return
    }
    setIsExpressingInterest(true)
    try {
      if (subscriptionId) {
        await createProxyIntroRequest({
          subscriptionId,
          candidateId: Number(candidateData.id),
          source: 'candidate_detail',
        })
      } else if (sessionId) {
        await expressDiscoveryCandidateInterest({
          sessionId,
          candidateId: candidateData.id,
        })
      } else {
        throw new Error('interest_unavailable')
      }
      setShowSubmittedHint(true)
    } catch (error) {
      notifyError(error, '发起意愿失败，请稍后重试')
    } finally {
      setIsExpressingInterest(false)
    }
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
          autoPlay
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
            onClick={() => {
              if (viewType === 'interest' && caseId) {
                void handleDecline()
              } else {
                onBack()
              }
            }}
            disabled={isExpressingInterest}
            className="flex-1 py-3 border border-border rounded-xl text-foreground font-medium hover:bg-secondary transition-colors focus-ring disabled:opacity-70"
            aria-label={viewType === 'interest' ? '暂不考虑这位候选人' : '暂时跳过这位候选人'}
          >
            {isExpressingInterest && viewType === 'interest' ? '处理中' : viewType === 'interest' ? '暂不考虑' : '暂时跳过'}
          </button>
          <Heartbeat>
            <button
              onClick={() => void handleExpressInterest()}
              disabled={isExpressingInterest || !canExpressInterest || showSubmittedHint}
              className="flex-1 py-3 bg-primary rounded-xl text-primary-foreground font-medium flex items-center justify-center gap-2 hover:bg-primary/90 transition-all focus-ring shadow-lg shadow-primary/20 disabled:opacity-70"
              aria-label={viewType === 'interest' ? `接受${candidateData.name}的认识请求` : `向${candidateData.name}发起认识意愿`}
            >
              <Heart className="w-4 h-4" aria-hidden="true" />
              {!canExpressInterest
                ? '暂不可发起'
                : showSubmittedHint
                  ? '已提交意愿'
                  : isExpressingInterest
                    ? '发送中'
                    : viewType === 'interest'
                      ? '愿意认识'
                      : '愿意认识TA'}
            </button>
          </Heartbeat>
        </div>
        {showSubmittedHint ? (
          <div className="mt-2 flex items-center justify-center gap-3">
            <p className="text-xs text-muted-foreground">已提交，对方回复后会在关系页更新</p>
            <button
              type="button"
              onClick={onOpenRelationships}
              className="text-xs font-medium text-primary"
            >
              去关系页
            </button>
          </div>
        ) : !canExpressInterest ? (
          <p className="mt-2 text-center text-xs text-muted-foreground">请先通过推荐来信进入后再发起认识</p>
        ) : null}
      </div>
    </PageTransition>
  )
}
