'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { MessageSquareHeart, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/her/ui/page-header'
import type { FeedbackCategory, FeedbackRecord } from '@/lib/feedback/types'
import { notifySuccess } from '@/lib/notify'

const categories = [
  { value: 'bug', label: '功能异常' },
  { value: 'ux', label: '体验问题' },
  { value: 'account', label: '账号相关' },
  { value: 'suggestion', label: '产品建议' },
]

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export default function FeedbackPage() {
  const router = useRouter()
  const [category, setCategory] = useState<FeedbackCategory>('bug')
  const [content, setContent] = useState('')
  const [contact, setContact] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [records, setRecords] = useState<FeedbackRecord[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function loadRecords() {
      setIsLoading(true)
      try {
        const response = await fetch('/api/feedback', { cache: 'no-store' })
        const payload = (await response.json()) as { records?: FeedbackRecord[]; error?: string }
        if (!response.ok) {
          throw new Error(payload.error || '反馈记录加载失败')
        }
        if (!cancelled) {
          setRecords(Array.isArray(payload.records) ? payload.records : [])
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '反馈记录加载失败')
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void loadRecords()

    return () => {
      cancelled = true
    }
  }, [])

  const latestRecords = useMemo(() => records.slice(0, 5), [records])

  const handleSubmit = () => {
    void (async () => {
      const trimmedContent = content.trim()
      const trimmedContact = contact.trim()

      if (trimmedContent.length < 10) {
        setError('请至少写 10 个字，方便我们判断问题')
        return
      }

      if (trimmedContact && trimmedContact.length < 5) {
        setError('联系方式太短了，请再确认一下')
        return
      }

      setIsSubmitting(true)
      try {
        const response = await fetch('/api/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category,
            content: trimmedContent,
            contact: trimmedContact,
          }),
        })
        const payload = (await response.json()) as {
          records?: FeedbackRecord[]
          error?: string
        }
        if (!response.ok) {
          throw new Error(payload.error || '反馈提交失败')
        }

        setRecords(Array.isArray(payload.records) ? payload.records : records)
        setContent('')
        setContact('')
        setError(null)
        notifySuccess('反馈已提交')
      } catch (submitError) {
        setError(submitError instanceof Error ? submitError.message : '反馈提交失败')
      } finally {
        setIsSubmitting(false)
      }
    })()
  }

  return (
    <div className="min-h-dvh bg-background">
      <PageHeader
        title="意见反馈"
        subtitle="描述你遇到的问题，我们会优先处理高频反馈"
        showBack
        onBack={() => router.back()}
      />

      <main className="mx-auto flex min-h-0 max-w-md flex-col gap-4 px-4 py-4 pb-10">
        <section className="rounded-xl border border-border bg-card p-4">
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-full bg-primary/10 p-2">
              <MessageSquareHeart className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h2 className="text-sm font-medium">提交反馈</h2>
              <p className="text-xs text-muted-foreground">越具体越容易定位问题</p>
            </div>
          </div>

          <div className="mb-4">
            <p className="mb-2 text-xs text-muted-foreground">问题类型</p>
            <div className="flex flex-wrap gap-2">
              {categories.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setCategory(item.value as FeedbackCategory)}
                  className={
                    item.value === category
                      ? 'rounded-full bg-primary px-3 py-1.5 text-xs text-primary-foreground'
                      : 'rounded-full bg-secondary px-3 py-1.5 text-xs text-secondary-foreground'
                  }
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-4">
            <label htmlFor="feedback-content" className="mb-2 block text-xs text-muted-foreground">
              问题描述
            </label>
            <textarea
              id="feedback-content"
              value={content}
              onChange={(event) => {
                setContent(event.target.value)
                setError(null)
              }}
              placeholder="例如：我在认证页上传学历材料后一直停留在审核中，返回“我的”页也没有更新。"
              className="min-h-36 w-full rounded-xl border border-border bg-background px-3 py-3 text-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/30"
              maxLength={500}
            />
            <div className="mt-2 flex justify-between text-xs text-muted-foreground">
              <span>建议写清楚页面、操作步骤和期望结果</span>
              <span>{content.length}/500</span>
            </div>
          </div>

          <div className="mb-4">
            <label htmlFor="feedback-contact" className="mb-2 block text-xs text-muted-foreground">
              联系方式（选填）
            </label>
            <input
              id="feedback-contact"
              value={contact}
              onChange={(event) => {
                setContact(event.target.value)
                setError(null)
              }}
              placeholder="手机号 / 微信号 / 邮箱"
              className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/30"
              maxLength={60}
            />
          </div>

          {error ? <p className="mb-3 text-sm text-destructive">{error}</p> : null}

          <Button
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="h-11 w-full rounded-xl"
          >
            <Send className="h-4 w-4" />
            {isSubmitting ? '提交中…' : '提交反馈'}
          </Button>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">最近提交</h2>
          {isLoading ? (
            <p className="mt-2 text-xs leading-5 text-muted-foreground">正在加载反馈记录…</p>
          ) : latestRecords.length === 0 ? (
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              你最近还没有提交过反馈。提交后会保存在当前服务端环境里，方便你回看自己提过什么问题。
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              {latestRecords.map((item) => {
                const categoryLabel = categories.find((entry) => entry.value === item.category)?.label || item.category
                return (
                  <div key={item.id} className="rounded-lg bg-secondary/40 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-medium text-foreground">{categoryLabel}</span>
                      <span className="text-xs text-muted-foreground">{formatTime(item.createdAt)}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-foreground">{item.content}</p>
                    {item.contact ? (
                      <p className="mt-2 text-xs text-muted-foreground">联系方式：{item.contact}</p>
                    ) : null}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
