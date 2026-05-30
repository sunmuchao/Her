'use client'

import { MessageSquare, Calendar, FileText } from 'lucide-react'
import { useCollectedStatements } from '@/lib/hooks/use-collected'
import { useMemo } from 'react'
import { PageHeader } from './ui/page-header'
import { PageErrorState } from './ui/error-handling'
import { DemoDataBanner } from './ui/demo-data-banner'
import { FadeIn, PageTransition } from './ui/animations'
import { CollectedPreferencesSkeleton } from './ui/skeletons/collected-preferences-skeleton'

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

/**
 * 已收集偏好页面
 *
 * 展示用户明确说过的择偶偏好
 * 使用 React Query hook 管理数据获取
 */
export default function CollectedPreferencesPage({ onBack }: CollectedPreferencesPageProps) {
  const { data, isLoading, error, isFetching } = useCollectedStatements()

  // 解析数据
  const items = useMemo(() => {
    const collectedItems = (data?.collected_items || {}) as Record<string, CollectedItem>
    if (Object.keys(collectedItems).length > 0) {
      return collectedItems
    }
    // fallback: 从 collected_statements 映射
    const statements = data?.collected_statements || {}
    const mapped: Record<string, CollectedItem> = {}
    for (const [key, value] of Object.entries(statements)) {
      mapped[key] = { value }
    }
    return mapped
  }, [data])

  // 判断是否使用 Mock 数据
  const usingMockData = useMemo(() => {
    return isFetching && !data
  }, [isFetching, data])

  // 加载状态 - 使用骨架屏
  if (isLoading) {
    return <CollectedPreferencesSkeleton onBack={onBack} />
  }

  // 错误状态 - 使用统一错误组件
  if (error) {
    return (
      <PageErrorState
        message={error instanceof Error ? error.message : '已收集偏好加载失败'}
        onRetry={() => window.location.reload()}
        variant="full"
      />
    )
  }

  const entries = Object.entries(items)

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {usingMockData && <DemoDataBanner />}

      {/* Header - 使用统一组件 */}
      <PageHeader
        title="已收集偏好"
        subtitle="仅展示你明确说过的内容"
        showBack
        onBack={onBack}
      />

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