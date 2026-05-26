'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, MessageSquare, Calendar, FileText } from 'lucide-react'
import { fetchCollectedStatements } from '@/lib/api/endpoints/collected'
import { getErrorMessage } from '@/lib/api/errors'
import { canUseMockFallback } from '@/lib/mock'
import { usePageDataSource } from '@/lib/data-provenance'
import { FadeIn, PageTransition } from './ui/animations'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'

export type CollectedItem = {
  value: unknown
  source_channel?: string
  collected_at?: string
  evidence?: string
  source_type?: string
}

const CHANNEL_LABELS: Record<string, string> = {
  matchmaker_chat: '红娘对话',
  candidate_chat: '候选对话',
  profile_form: '资料填写',
}

const FIELD_LABELS: Record<string, string> = {
  target_age_min: '年龄下限',
  target_age_max: '年龄上限',
  target_cities: '城市偏好',
  target_education_min: '学历要求',
  target_gender: '性别偏好',
  must_have_tags: '必须有',
  must_not_have_tags: '不接受',
  preferred_traits: '偏好特质',
  disliked_traits: '不喜欢',
}

function formatFieldLabel(field: string): string {
  return FIELD_LABELS[field] || field
}

function formatChannel(channel?: string): string {
  if (!channel) return '未知来源'
  return CHANNEL_LABELS[channel] || channel
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.map(String).join('、')
  return String(value)
}

interface CollectedPreferencesPageProps {
  onBack: () => void
}

export default function CollectedPreferencesPage({ onBack }: CollectedPreferencesPageProps) {
  const [items, setItems] = useState<Record<string, CollectedItem>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const { usingMockData, applyProvenance } = usePageDataSource()
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setLoadError(null)
      try {
        const data = await fetchCollectedStatements()
        if (cancelled) return
        const collectedItems = (data.collected_items || {}) as Record<string, CollectedItem>
        if (Object.keys(collectedItems).length) {
          setItems(collectedItems)
        } else {
          const flat = data.collected_statements || {}
          const mapped: Record<string, CollectedItem> = {}
          for (const [key, value] of Object.entries(flat)) {
            mapped[key] = { value }
          }
          setItems(mapped)
        }
        applyProvenance(false, Object.keys(collectedItems).length > 0 || Object.keys(data.collected_statements || {}).length > 0)
      } catch (error) {
        if (cancelled) return
        setLoadError(getErrorMessage(error, '已收集偏好加载失败'))
        if (canUseMockFallback()) {
          applyProvenance(true, true)
          setItems({
            target_age_min: { value: 25, source_channel: 'matchmaker_chat', collected_at: '2026-05-01' },
            target_age_max: { value: 32, source_channel: 'matchmaker_chat', collected_at: '2026-05-01' },
            target_cities: {
              value: '上海',
              source_channel: 'matchmaker_chat',
              evidence: '对话中明确提到城市=上海',
            },
          })
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [applyProvenance])

  if (isLoading) {
    return (
      <PageTransition className="flex flex-col h-full bg-background items-center justify-center">
        <p className="text-sm text-muted-foreground">加载已收集偏好…</p>
      </PageTransition>
    )
  }

  if (loadError && !canUseMockFallback()) {
    return <ErrorState message={loadError} onRetry={() => window.location.reload()} />
  }

  const entries = Object.entries(items)

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {usingMockData && <DemoDataBanner />}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="w-8 h-8 flex items-center justify-center focus-ring rounded-full"
            aria-label="返回"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-medium">已收集偏好</h1>
            <p className="text-xs text-muted-foreground">仅展示你明确说过的内容</p>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 pb-20">
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-12">
            还没有收集到偏好，和红娘聊聊你的期待吧
          </p>
        ) : (
          entries.map(([field, item], index) => (
            <FadeIn key={field} delay={index * 40}>
              <section className="bg-card border border-border rounded-xl p-4 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-medium text-sm">{formatFieldLabel(field)}</h2>
                  <span className="text-sm text-foreground">{formatValue(item.value)}</span>
                </div>
                <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <MessageSquare className="w-3 h-3" aria-hidden="true" />
                    {formatChannel(item.source_channel)}
                  </span>
                  {item.collected_at ? (
                    <span className="inline-flex items-center gap-1">
                      <Calendar className="w-3 h-3" aria-hidden="true" />
                      {item.collected_at}
                    </span>
                  ) : null}
                </div>
                {item.evidence ? (
                  <p className="text-xs text-muted-foreground flex gap-1.5">
                    <FileText className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
                    {item.evidence}
                  </p>
                ) : null}
              </section>
            </FadeIn>
          ))
        )}
      </div>
    </PageTransition>
  )
}
