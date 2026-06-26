'use client'

import { ArrowLeft, BadgeCheck, MapPin, Heart, MessageCircle, CheckCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { CandidatePreview } from '@/lib/types/candidate'
import { fetchCandidateDetail, fetchCandidateXiaoyaAnalysis } from '@/lib/api/endpoints/candidates'
import type { TrustSummary } from '@/lib/api/endpoints/trust'
import { formatExplainSourceMap } from '@/lib/api/endpoints/collected'
import { GatewayClientError } from '@/lib/api/client'
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
import {
  createProxyIntroRequest,
  replyProxyIntroCase,
  fetchMyProxyIntroCases,
} from '@/lib/api/endpoints/proxy-intro'
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
  const [xiaoyaStructured, setXiaoyaStructured] = useState<{
    summary?: string
    riskPoint?: string
    firstQuestion?: string
  } | null>(null)
  const [apiDetail, setApiDetail] = useState<{
    headline?: string
    selfIntro?: string
    images?: string[]
    matchReasons?: string[]
  } | null>(null)
  const [xiaoyaAnalysis, setXiaoyaAnalysis] = useState<string>('')
  const [xiaoyaLoading, setXiaoyaLoading] = useState(false)
  const [xiaoyaError, setXiaoyaError] = useState<string | null>(null)
  const [xiaoyaReloadToken, setXiaoyaReloadToken] = useState(0)
  const [profileFacts, setProfileFacts] = useState<Record<string, unknown>>({})
  const [collectedMatchReasons, setCollectedMatchReasons] = useState<string[]>([])
  const [trustLabels, setTrustLabels] = useState<string[]>([])
  const [trustSummary, setTrustSummary] = useState<TrustSummary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadErrorTitle, setLoadErrorTitle] = useState<string>('加载失败')
  const [usingMockData, setUsingMockData] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isExpressingInterest, setIsExpressingInterest] = useState(false)
  const [showSubmittedHint, setShowSubmittedHint] = useState(false)

  function xiaoyaCacheKey(candidateIdValue: string, sessionIdValue: string) {
    return `xiaoya-analysis:${sessionIdValue}:${candidateIdValue}`
  }

  function formatHeight(value: unknown): string {
    const num = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(num) && num > 0 ? `${num}cm` : ''
  }

  function formatIncome(value: unknown): string {
    if (value == null || value === '') return ''
    return String(value)
  }

  function normalizeVerificationStatus(value: unknown): 'verified' | 'self_reported' | 'unknown' {
    const normalized = String(value || '').trim().toLowerCase()
    if (['verified', 'approved', 'passed', 'id_verified'].includes(normalized)) return 'verified'
    if (normalized) return 'self_reported'
    return 'unknown'
  }

  function formatStatusMeta(value: unknown): { label: string; className: string } {
    const status = normalizeVerificationStatus(value)
    if (status === 'verified') {
      return { label: '已核验', className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' }
    }
    if (status === 'self_reported') {
      return { label: '本人填写', className: 'bg-slate-500/10 text-slate-700 dark:text-slate-300' }
    }
    return { label: '', className: '' }
  }

  function normalizeXiaoyaStructured(value: unknown) {
    if (!value || typeof value !== 'object') return null
    const record = value as {
      summary?: unknown
      risk_point?: unknown
      first_question?: unknown
    }
    const rawSummary = String(record.summary || '').trim()
    const rawRiskPoint = String(record.risk_point || '').trim()
    const rawFirstQuestion = String(record.first_question || '').trim()
    const combinedRawText = [rawSummary, rawRiskPoint, rawFirstQuestion].filter(Boolean).join(' ')
    const reparsed = parseLabeledXiaoyaText(combinedRawText)
    const normalized = reparsed || {
      summary: rawSummary,
      riskPoint: rawRiskPoint,
      firstQuestion: rawFirstQuestion,
    }
    if (!normalized.summary && !normalized.riskPoint && !normalized.firstQuestion) return null
    return normalized
  }

  function parseLabeledXiaoyaText(text: string) {
    const normalizedText = String(text || '').trim()
    if (!normalizedText) return null
    const pattern = /(匹配点|风险点|先确认)[：:]\s*/g
    const matches = Array.from(normalizedText.matchAll(pattern))
    if (matches.length === 0) return null
    const sections = {
      summary: '',
      riskPoint: '',
      firstQuestion: '',
    }
    const fieldMap: Record<string, 'summary' | 'riskPoint' | 'firstQuestion'> = {
      匹配点: 'summary',
      风险点: 'riskPoint',
      先确认: 'firstQuestion',
    }
    matches.forEach((match, index) => {
      const label = match[1]
      const start = match.index! + match[0].length
      const end = index + 1 < matches.length ? matches[index + 1].index! : normalizedText.length
      sections[fieldMap[label]] = normalizedText.slice(start, end).trim().replace(/^[；;，,\s]+|[；;，,\s]+$/g, '')
    })
    if (!sections.summary && !sections.riskPoint && !sections.firstQuestion) return null
    return sections
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
          caseId: candidate?.caseId,
          cardId: candidate?.cardId,  // 新增：传递cardId参数用于权限验证
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
          matchReasons: view?.caution_sections?.[0]?.items,
        })
        setXiaoyaAnalysis('')
        setXiaoyaError(null)
        setTrustSummary(data.trust_summary || null)
        setTrustLabels(data.trust_summary?.labels || [])
        if (data.explain?.source_map) {
          setCollectedMatchReasons(formatExplainSourceMap(data.explain.source_map))
        }
        setUsingMockData(false)
      } catch (error) {
        if (cancelled) return
        if (error instanceof GatewayClientError && error.status === 401) {
          setLoadErrorTitle('登录已失效')
          setLoadError('请重新登录后再查看这位候选人')
        } else if (error instanceof GatewayClientError && error.status === 403) {
          setLoadErrorTitle('暂时无法查看')
          setLoadError('请从发现页或推荐入口进入后再查看详情')
        } else {
          setLoadErrorTitle('加载失败')
          setLoadError(getErrorMessage(error, '资料详情加载失败'))
        }
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

  useEffect(() => {
    let cancelled = false
    const abortController = new AbortController()

    // Unified cleanup function - always defined at the start
    const cleanup = () => {
      cancelled = true
      abortController.abort()
    }

    if (!sessionId) {
      setXiaoyaAnalysis('')
      setXiaoyaStructured(null)
      setXiaoyaLoading(false)
      setXiaoyaError(null)
      return cleanup // ✅ Early return also provides cleanup
    }

    async function loadXiaoyaAnalysis() {
      const cacheKey = xiaoyaCacheKey(String(candidateId), sessionId || '')
      const isManualReload = xiaoyaReloadToken > 0

      // 使用 localStorage 作为持久化缓存（有效期 24 小时）
      const cachePrefix = 'xiaoya-analysis-cache:'
      const fullCacheKey = cachePrefix + cacheKey

      if (typeof window !== 'undefined' && isManualReload) {
        window.localStorage.removeItem(fullCacheKey)
      }

      if (typeof window !== 'undefined' && !isManualReload) {
        try {
          const cachedRaw = window.localStorage.getItem(fullCacheKey)
          if (cachedRaw) {
            const cached = JSON.parse(cachedRaw) as {
              text?: unknown
              structured?: unknown
              timestamp?: number
            }
            // 检查缓存是否过期（24 小时）
            const cacheAge = cached.timestamp ? Date.now() - cached.timestamp : 0
            const maxAgeMs = 24 * 60 * 60 * 1000 // 24 小时
            if (cacheAge < maxAgeMs) {
              const cachedText = String(cached.text || '').trim()
              const cachedStructured =
                normalizeXiaoyaStructured(cached.structured) || parseLabeledXiaoyaText(cachedText)
              if (cachedText || cachedStructured) {
                setXiaoyaAnalysis(cachedText)
                setXiaoyaStructured(cachedStructured)
                setXiaoyaLoading(false)
                setXiaoyaError(null)
                console.log('[小雅分析] 使用缓存，无需重新生成')
                return // 直接返回，不调用 AI
              }
            } else {
              console.log('[小雅分析] 缓存已过期，重新生成')
              window.localStorage.removeItem(fullCacheKey)
            }
          }
        } catch (e) {
          console.warn('[小雅分析] 缓存解析失败，重新生成', e)
          window.localStorage.removeItem(fullCacheKey)
        }
      }

      // 无缓存或缓存失效 → 显示占位符，开始生成
      setXiaoyaLoading(true)
      setXiaoyaAnalysis('')
      setXiaoyaStructured(null)
      setXiaoyaError(null)

      console.log('[小雅分析] 开始异步生成，页面继续渲染...')

      try {
        const data = await fetchCandidateXiaoyaAnalysis({
          candidateId,
          sessionId: sessionId || '',
          refreshKey: isManualReload ? xiaoyaReloadToken : undefined,
          signal: abortController.signal, // ✅ Pass AbortSignal to cancel request
        })
        if (cancelled) return
        const text = String(data.xiaoya_analysis || '').trim()
        const structured =
          normalizeXiaoyaStructured(data.xiaoya_analysis_structured) || parseLabeledXiaoyaText(text)
        if (!text) {
          setXiaoyaAnalysis('')
          setXiaoyaStructured(null)
          setXiaoyaError('小雅分析生成失败，请稍后重试')
          return
        }
        setXiaoyaAnalysis(text)
        setXiaoyaStructured(structured)

        // 保存到 localStorage（带时间戳）
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(
            fullCacheKey,
            JSON.stringify({
              text,
              structured: data.xiaoya_analysis_structured || null,
              timestamp: Date.now(), // 记录缓存时间
            }),
          )
          console.log('[小雅分析] 已缓存到 localStorage，24小时内有效')
        }
      } catch (err) {
        // Handle AbortError separately - request was cancelled
        if (err instanceof Error && err.name === 'AbortError') {
          console.log('[小雅分析] 请求已取消，用户离开页面')
          return
        }
        if (!cancelled) {
          setXiaoyaAnalysis('')
          setXiaoyaStructured(null)
          setXiaoyaError('小雅分析生成失败，请稍后重试')
          if (typeof window !== 'undefined') {
            window.localStorage.removeItem(fullCacheKey)
          }
        }
      } finally {
        if (!cancelled) {
          setXiaoyaLoading(false)
          console.log('[小雅分析] 生成完成，页面更新')
        }
      }
    }

    void loadXiaoyaAnalysis()
    return cleanup // ✅ Always return cleanup
  }, [candidateId, sessionId, xiaoyaReloadToken])

  const rawCandidate = usingMockData
    ? (DEMO_CANDIDATES_DATABASE[candidateId] || DEFAULT_DEMO_CANDIDATE)
    : null
  const subscriptionId = candidate?.subscriptionId
  const resolvedCandidateId = candidate?.id || candidateId
  // 主动发起场景：需要有 candidateId 和 subscriptionId/sessionId
  // 被动推荐场景：只需要有 caseId
  const canExpressInterest = viewType === 'interest' && caseId
    ? Boolean(caseId)
    : Boolean(resolvedCandidateId && (subscriptionId || sessionId))

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
    profileFacts.city ? { label: '城市', value: String(profileFacts.city), fieldKey: 'city' } : null,
    profileFacts.age ? { label: '年龄', value: String(profileFacts.age), fieldKey: 'age' } : null,
    profileFacts.job ? { label: '职业', value: String(profileFacts.job), fieldKey: 'job' } : null,
    profileFacts.education ? { label: '学历', value: String(profileFacts.education), fieldKey: 'education' } : null,
    profileFacts.relationship_goal ? { label: '关系目标', value: String(profileFacts.relationship_goal), fieldKey: 'relationship_goal' } : null,
    profileFacts.marital_status ? { label: '婚况', value: String(profileFacts.marital_status), fieldKey: 'marital_status' } : null,
    formatHeight(profileFacts.height) ? { label: '身高', value: formatHeight(profileFacts.height), fieldKey: 'height' } : null,
    profileFacts.income_range ? { label: '收入', value: formatIncome(profileFacts.income_range), fieldKey: 'income' } : null,
  ].filter((item): item is { label: string; value: string; fieldKey: string } => Boolean(item))

  const verifiedFieldMap = trustSummary?.field_verifications || {}
  const incomeHint =
    collectedMatchReasons.find((item) => item.includes('收入')) ||
    apiDetail?.matchReasons?.find((item) => item.includes('收入')) ||
    ''
  const compactIncomeHint = incomeHint
    ? incomeHint.replace('收入仍为自填信息，建议仅将其视为参考', '收入为自填，仅供参考')
    : ''
  const sourceNote =
    trustLabels.length > 0
      ? '带标签的信息经过平台核验，其余内容主要来自本人填写。'
      : '当前资料以本人填写为主，建议认识前确认关键条件。'

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
        matchReasons:
          collectedMatchReasons.length
            ? collectedMatchReasons
            : apiDetail?.matchReasons || (candidate?.matchReason ? [candidate.matchReason] : []),
      }

  const headlineText = String(candidateData.headline || '').replace(/[“”"]/g, '').trim()
  const heroMetaParts = [candidateData.occupation, candidateData.education]
    .map((item) => String(item || '').trim())
    .filter(Boolean)
  const shouldShowHeadline =
    Boolean(headlineText) &&
    !heroMetaParts.some((part) => headlineText.includes(part)) &&
    headlineText !== String(candidateData.city || '').trim()
  const xiaoyaSections = xiaoyaStructured
    ? [
        xiaoyaStructured.summary ? { label: '匹配点', value: xiaoyaStructured.summary } : null,
        xiaoyaStructured.riskPoint ? { label: '风险点', value: xiaoyaStructured.riskPoint } : null,
        xiaoyaStructured.firstQuestion ? { label: '先确认', value: xiaoyaStructured.firstQuestion } : null,
      ].filter((item): item is { label: string; value: string } => Boolean(item))
    : []

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
        <ErrorState title={loadErrorTitle} message={loadError} onBack={onBack} />
      </PageTransition>
    )
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
          {shouldShowHeadline ? (
            <p className="text-white/80 italic mb-3 text-balance">&ldquo;{candidateData.headline}&rdquo;</p>
          ) : null}
          <div className="flex items-center gap-4 text-sm text-white/70">
            <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" aria-hidden="true" />{candidateData.city}</span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-4 py-5 space-y-4 pb-28">
        {/* Self intro */}
        <FadeIn delay={100}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="mb-3">
              <h3 className="font-medium">自我介绍</h3>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">{candidateData.selfIntro}</p>
          </section>
        </FadeIn>

        <FadeIn delay={180}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <BadgeCheck className="w-4 h-4 text-primary" aria-hidden="true" />
              <h3 className="font-medium">基本资料</h3>
            </div>
            {(trustLabels.length
              ? trustLabels.map((label) => ({ name: label, verified: true }))
              : DEMO_VERIFIED_ITEMS
            ).length > 0 ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {(trustLabels.length
                  ? trustLabels.map((label) => ({ name: label, verified: true }))
                  : DEMO_VERIFIED_ITEMS
                ).map((item, i) => (
                  <div
                    key={i}
                    className={cn(
                      'flex items-center gap-2 rounded-full px-3 py-1.5 text-xs transition-colors',
                      item.verified ? 'bg-primary/10 text-primary' : 'bg-secondary text-muted-foreground'
                    )}
                  >
                    {item.verified ? <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" /> : <div className="h-3.5 w-3.5 rounded-full border-2 border-current" aria-hidden="true" />}
                    {item.name}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {factKeyPoints.map((point, i) => {
                const statusMeta = formatStatusMeta(verifiedFieldMap[point.fieldKey])
                return (
                  <div key={i} className="rounded-xl border border-border bg-background/80 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs text-muted-foreground">{point.label}</span>
                      {statusMeta.label ? (
                        <span className={cn('rounded-full px-2 py-1 text-[11px] font-medium', statusMeta.className)}>
                          {statusMeta.label}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-2 text-sm font-medium text-foreground">{point.value}</p>
                    {point.fieldKey === 'income' && compactIncomeHint ? (
                      <p className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-300">{compactIncomeHint}</p>
                    ) : null}
                  </div>
                )
              })}
            </div>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">{sourceNote}</p>
          </section>
        </FadeIn>

        {/* Matchmaker note - 仅在推荐场景显示 */}
      {/* 已匹配的候选人（matched 类型）不显示小雅分析，因为用户已经建立关系 */}
      {viewType !== 'matched' && (
        <FadeIn delay={260}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <MessageCircle className="w-4 h-4 text-primary" aria-hidden="true" />
              <h3 className="font-medium">小雅分析</h3>
            </div>
            {xiaoyaLoading ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground leading-relaxed">
                  小雅正在结合你们两个人的资料深度分析匹配度，生成时间约 30-60 秒，请耐心等待...
                </p>
                <div className="space-y-2" aria-hidden="true">
                  <div className="h-3 w-full animate-pulse rounded-full bg-secondary" />
                  <div className="h-3 w-11/12 animate-pulse rounded-full bg-secondary" />
                  <div className="h-3 w-4/5 animate-pulse rounded-full bg-secondary" />
                </div>
              </div>
            ) : xiaoyaSections.length > 0 ? (
              <div className="space-y-3">
                {xiaoyaSections.map((section) => (
                  <div key={section.label} className="rounded-xl border border-border bg-background/80 p-3">
                    <p className="text-xs font-medium tracking-wide text-primary">{section.label}</p>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{section.value}</p>
                  </div>
                ))}
              </div>
            ) : xiaoyaAnalysis ? (
              <p className="text-sm text-muted-foreground leading-relaxed">{xiaoyaAnalysis}</p>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {xiaoyaError || '小雅分析生成失败，请稍后重试'}
                </p>
                {sessionId ? (
                  <button
                    type="button"
                    onClick={() => setXiaoyaReloadToken((value) => value + 1)}
                    className="text-sm font-medium text-primary"
                  >
                    重新获取分析
                  </button>
                ) : null}
              </div>
            )}
          </section>
        </FadeIn>
      )}
      </div>

      {/* Bottom CTA with heartbeat animation */}
      {/* 已匹配的候选人（matched 类型）不显示操作按钮 */}
      {viewType !== 'matched' && (
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
                      : '愿意认识'}
            </button>
          </Heartbeat>
        </div>
        {showSubmittedHint ? (
          <div className="mt-2 flex items-center justify-center gap-3">
            <p className="text-xs text-muted-foreground">已提交，后续进展会在关系页更新</p>
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
      )}
    </PageTransition>
  )
}
