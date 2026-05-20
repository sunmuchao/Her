'use client'

import { useEffect, useState } from 'react'
import Image from 'next/image'
import {
  ArrowLeft,
  BadgeCheck,
  Loader2,
  MapPin,
  MessageCircle,
  Shield,
  Sparkles,
} from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface CandidateDetailPageProps {
  candidateId: string
  sessionId?: string
  runtimeContext: HerRuntimeContext
  onBack: () => void
  onStartChat: (chatId: string) => void
}

type DetailView = {
  hero?: {
    name?: string
    age?: number | string | null
    city?: string | null
    headline?: string | null
  }
  photo_gallery?: Array<{ image_url?: string | null }>
  verified_sections?: Array<{ title: string; items: string[] }>
  self_reported_sections?: Array<{ title: string; items: string[] }>
  caution_sections?: Array<{ title: string; items: string[] }>
  matchmaker_notes?: string[]
}

type DetailResponse = {
  profile_id: number
  detail_view: DetailView
}

export default function CandidateDetailPage({
  candidateId,
  sessionId,
  runtimeContext,
  onBack,
  onStartChat,
}: CandidateDetailPageProps) {
  const [data, setData] = useState<DetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [primaryConversationId, setPrimaryConversationId] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function loadDetail() {
      setLoading(true)
      setError(null)
      try {
        const next = await gatewayJson<DetailResponse>(
          `/v1/discovery/profiles/${candidateId}${queryString({ session_id: sessionId })}`,
        )
        if (!active) {
          return
        }
        setData(next)
        setCurrentImageIndex(0)
      } catch (err) {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : '资料详情加载失败')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadDetail()
    return () => {
      active = false
    }
  }, [candidateId, sessionId])

  useEffect(() => {
    let active = true

    async function loadPrimaryConversation() {
      if (!runtimeContext.caseId || !runtimeContext.userId) {
        setPrimaryConversationId(null)
        return
      }
      try {
        const payload = await gatewayJson<{
          conversations: Array<{
            conversation: { conversation_id: string; layout_role?: string }
          }>
        }>(
          `/v2/chat/cases/${runtimeContext.caseId}/timeline${queryString({
            requester_id: runtimeContext.userId,
          })}`,
        )
        if (!active) {
          return
        }
        const first =
          payload.conversations.find((item) => item.conversation.layout_role === 'main_group') ||
          payload.conversations[0]
        setPrimaryConversationId(first?.conversation.conversation_id || null)
      } catch {
        if (active) {
          setPrimaryConversationId(null)
        }
      }
    }

    loadPrimaryConversation()
    return () => {
      active = false
    }
  }, [runtimeContext.caseId, runtimeContext.userId])

  const detailView = data?.detail_view
  const hero = detailView?.hero || {}
  const photos = (detailView?.photo_gallery || []).filter((item) => item.image_url)
  const currentImage = photos[currentImageIndex]?.image_url || '/placeholder-user.jpg'
  const canOpenChat = Boolean(primaryConversationId)

  return (
    <div className="min-h-screen bg-background max-w-md mx-auto">
      <div className="relative">
        <div className="relative h-[540px] overflow-hidden">
          <Image
            src={currentImage}
            alt={hero.name || '候选人'}
            fill
            className="object-cover"
            unoptimized={currentImage.startsWith('http')}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#1a1714] via-[#1a1714]/20 to-transparent" />
          <div className="absolute top-0 inset-x-0 h-32 bg-gradient-to-b from-foreground/45 to-transparent" />

          <button
            onClick={onBack}
            className="absolute top-12 left-5 z-10 flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-background/20 backdrop-blur-xl"
          >
            <ArrowLeft className="h-5 w-5 text-white" />
          </button>

          <div className="absolute bottom-0 left-0 right-0 p-6 pb-8 text-white">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-white/10 bg-white/15 px-3 py-1 text-xs">
                平台资料详情
              </span>
              {detailView?.verified_sections?.length ? (
                <span className="rounded-full border border-white/10 bg-white/15 px-3 py-1 text-xs inline-flex items-center gap-1">
                  <BadgeCheck className="h-3.5 w-3.5 text-gold" />
                  已核验信息
                </span>
              ) : null}
            </div>
            <div className="flex items-end gap-3">
              <h1 className="editorial-title text-5xl tracking-tight">{hero.name || '候选人'}</h1>
              {hero.age ? <span className="text-2xl text-white/70">{hero.age}</span> : null}
            </div>
            <p className="mt-2 text-lg italic text-white/80">{hero.headline || '先看整体资料，再决定要不要继续了解。'}</p>
            {hero.city ? (
              <p className="mt-3 inline-flex items-center gap-1.5 text-sm text-white/75">
                <MapPin className="h-4 w-4" />
                {hero.city}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="bg-gradient-to-b from-background via-background to-blush/10 px-5 py-6 pb-36">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            正在加载资料详情
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : (
          <div className="space-y-5">
            {photos.length > 1 ? (
              <section className="rounded-2xl bg-card p-4 shadow-soft border border-border/30">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground">照片</h3>
                  <span className="text-xs text-muted-foreground">{photos.length} 张</span>
                </div>
                <div className="flex gap-3 overflow-x-auto">
                  {photos.map((item, index) => (
                    <button
                      key={`${item.image_url}-${index}`}
                      onClick={() => setCurrentImageIndex(index)}
                      className={`relative h-24 w-20 shrink-0 overflow-hidden rounded-2xl border ${
                        index === currentImageIndex ? 'border-primary' : 'border-border/30'
                      }`}
                    >
                      <Image
                        src={item.image_url || '/placeholder-user.jpg'}
                        alt={`照片 ${index + 1}`}
                        fill
                        className="object-cover"
                        unoptimized={String(item.image_url || '').startsWith('http')}
                      />
                    </button>
                  ))}
                </div>
              </section>
            ) : null}

            {(detailView?.verified_sections || []).map((section) => (
              <section key={section.title} className="rounded-2xl bg-card p-5 shadow-soft border border-border/30">
                <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Shield className="h-4 w-4 text-primary" />
                  {section.title}
                </h3>
                <div className="space-y-2">
                  {section.items.map((item) => (
                    <div key={item} className="rounded-xl bg-green-50 px-3 py-2 text-sm text-green-800">
                      {item}
                    </div>
                  ))}
                </div>
              </section>
            ))}

            {(detailView?.self_reported_sections || []).map((section) => (
              <section key={section.title} className="rounded-2xl bg-card p-5 shadow-soft border border-border/30">
                <h3 className="mb-4 text-sm font-semibold text-foreground">{section.title}</h3>
                <div className="space-y-3">
                  {section.items.map((item) => (
                    <p key={item} className="text-sm leading-6 text-taupe whitespace-pre-wrap">
                      {item}
                    </p>
                  ))}
                </div>
              </section>
            ))}

            {(detailView?.caution_sections || []).map((section) => (
              <section
                key={section.title}
                className="rounded-2xl border border-rose-soft/40 bg-gradient-to-r from-blush/50 to-card p-5 shadow-soft"
              >
                <h3 className="mb-3 text-sm font-semibold text-foreground">{section.title}</h3>
                <div className="space-y-2">
                  {section.items.map((item) => (
                    <p key={item} className="text-sm leading-6 text-taupe">
                      {item}
                    </p>
                  ))}
                </div>
              </section>
            ))}

            {(detailView?.matchmaker_notes || []).length ? (
              <section className="rounded-2xl bg-gradient-to-br from-rose-soft/30 via-blush/20 to-gold-soft/20 p-5 shadow-soft">
                <h3 className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Sparkles className="h-4 w-4 text-primary" />
                  红娘备注
                </h3>
                <div className="space-y-3">
                  {detailView?.matchmaker_notes?.map((item) => (
                    <p key={item} className="text-sm leading-6 text-taupe">
                      {item}
                    </p>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 mx-auto max-w-md border-t border-border/30 bg-background/90 px-5 pb-6 pt-4 backdrop-blur-xl safe-area-bottom">
        <button
          onClick={() => {
            if (primaryConversationId) {
              onStartChat(primaryConversationId)
            }
          }}
          disabled={!canOpenChat}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-primary to-rose px-4 py-4 text-sm font-medium text-primary-foreground shadow-elevated disabled:opacity-50"
        >
          <MessageCircle className="h-4 w-4" />
          {canOpenChat ? '进入当前关系聊天' : '当前后端未提供从详情直接建会话的用户端入口'}
        </button>
      </div>
    </div>
  )
}
