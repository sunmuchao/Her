'use client'

import { useEffect, useState } from 'react'
import {
  Settings,
  ChevronRight,
  BadgeCheck,
  Heart,
  MapPin,
  Briefcase,
  GraduationCap,
  Edit3,
  Shield,
  Bell,
  HelpCircle,
  CheckCircle,
  Clock,
  XCircle,
} from 'lucide-react'
import Image from 'next/image'
import { fetchAuthMe } from '@/lib/auth/auth-api'
import { ensureDevAuthSession } from '@/lib/auth/dev-bootstrap'
import { applyAuthMePayload, getAccessToken } from '@/lib/auth/session'
import { getErrorMessage } from '@/lib/api/errors'
import { canUseMockFallback } from '@/lib/mock'
import { isAuthStubEnabled } from '@/lib/env'
import { cn } from '@/lib/utils'
import { ProgressRing } from './ui/progress-ring'
import { FadeIn, PageTransition } from './ui/animations'
import { ThemeToggle } from './ui/theme-toggle'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'

interface ProfilePageProps {
  onStartVerification: () => void
  onOpenTrustCenter?: () => void
}

const fallbackProfile = {
  name: '用户',
  age: undefined as number | undefined,
  city: '待完善',
  avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200&h=200&fit=crop&crop=face',
  headline: '登录后完善你的资料',
  verified: false,
  occupation: '待完善',
  education: '',
  relationshipGoal: '',
}

const fallbackTags = ['待完善']

const fallbackPreferences: Record<string, string> = {
  ageRange: '待设置',
  location: '待设置',
  education: '待设置',
  height: '待设置',
}

const verificationItems = [
  { name: '身份', status: 'verified' as const },
  { name: '学历', status: 'verified' as const },
  { name: '职业', status: 'pending' as const },
  { name: '收入', status: 'unverified' as const },
]

const menuItems = [
  { icon: Edit3, label: '编辑资料' },
  { icon: Heart, label: '理想类型', badge: '已设置' },
  { icon: Bell, label: '通知设置' },
  { icon: HelpCircle, label: '帮助中心' },
]

export default function ProfilePage({ onStartVerification, onOpenTrustCenter }: ProfilePageProps) {
  const [profile, setProfile] = useState(fallbackProfile)
  const [tags, setTags] = useState(fallbackTags)
  const [preferences, setPreferences] = useState(fallbackPreferences)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setLoadError(null)

      let token = getAccessToken()
      if (!token && isAuthStubEnabled()) {
        const ok = await ensureDevAuthSession()
        if (cancelled) return
        token = ok ? getAccessToken() : null
      }

      if (!token) {
        if (canUseMockFallback()) {
          setUsingMockData(true)
          setProfile({
            name: '苏晴',
            age: 26,
            city: '上海',
            avatar: fallbackProfile.avatar,
            headline: '相信美好，期待遇见',
            verified: true,
            occupation: '市场经理',
            education: '上海交通大学 · 硕士',
            relationshipGoal: '认真恋爱，期待结婚',
          })
          setTags(['温柔', '独立', '爱阅读'])
        } else {
          setLoadError('请先登录后查看个人资料')
        }
        setIsLoading(false)
        return
      }

      try {
        const data = await fetchAuthMe()
        if (cancelled) return
        applyAuthMePayload(data)
        const user = data.user || {}
        const rawProfile = (data.profile || {}) as Record<string, unknown>
        setProfile({
          name: String(user.display_name || rawProfile.name || '用户'),
          age: typeof rawProfile.age === 'number' ? rawProfile.age : undefined,
          city: String(rawProfile.city || rawProfile.settlement_city || '待完善'),
          avatar: String(user.avatar_url || rawProfile.avatar_url || fallbackProfile.avatar),
          headline: String(rawProfile.headline || rawProfile.bio || '认真关系，从认真了解开始'),
          verified: Boolean(rawProfile.verified || rawProfile.live_video_verified),
          occupation: String(rawProfile.job || rawProfile.occupation || '待完善'),
          education: String(rawProfile.education || ''),
          relationshipGoal: String(rawProfile.relationship_goal || ''),
        })
        setUsingMockData(false)
        setLoadError(null)
      } catch (error) {
        if (cancelled) return
        setLoadError(getErrorMessage(error, '资料加载失败'))
        if (canUseMockFallback()) {
          setUsingMockData(true)
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  const getStatusIcon = (status: string) => {
    if (status === 'verified') return <CheckCircle className="w-4 h-4 text-primary" />
    if (status === 'pending') return <Clock className="w-4 h-4 text-gold" />
    return <XCircle className="w-4 h-4 text-muted-foreground" />
  }

  const verifiedCount = verificationItems.filter((i) => i.status === 'verified').length
  const verificationProgress = (verifiedCount / verificationItems.length) * 100

  if (isLoading) {
    return (
      <PageTransition className="flex flex-col h-full bg-background items-center justify-center">
        <p className="text-sm text-muted-foreground">加载资料中…</p>
      </PageTransition>
    )
  }

  if (loadError && !canUseMockFallback()) {
    return <ErrorState message={loadError} onRetry={() => window.location.reload()} />
  }

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {usingMockData && <DemoDataBanner />}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-medium">我的</h1>
          <div className="flex items-center gap-2">
            <ThemeToggle size="sm" />
            <button
              type="button"
              className="w-8 h-8 flex items-center justify-center focus-ring rounded-full"
              aria-label="设置"
            >
              <Settings className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        <FadeIn delay={100}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="relative">
                <div className="w-16 h-16 rounded-full overflow-hidden">
                  <Image
                    src={profile.avatar}
                    alt={profile.name}
                    width={64}
                    height={64}
                    className="object-cover"
                  />
                </div>
                {profile.verified && (
                  <BadgeCheck
                    className="absolute -bottom-0.5 -right-0.5 w-5 h-5 text-primary bg-background rounded-full"
                    aria-label="已认证"
                  />
                )}
              </div>
              <div>
                <h2 className="font-medium">
                  {profile.name}
                  {profile.age ? `，${profile.age}` : ''}
                </h2>
                <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3 h-3" aria-hidden="true" />
                    {profile.city}
                  </span>
                  <span>{profile.occupation}</span>
                </div>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mb-3">{profile.headline}</p>
            <div className="flex flex-wrap gap-1.5">
              {tags.map((tag, i) => (
                <span
                  key={i}
                  className="px-2 py-1 bg-secondary text-xs text-muted-foreground rounded-md"
                >
                  {tag}
                </span>
              ))}
            </div>
          </section>
        </FadeIn>

        <FadeIn delay={200}>
          <section>
            <button
              type="button"
              onClick={onOpenTrustCenter || onStartVerification}
              className="w-full bg-card border border-border rounded-xl p-4 text-left hover:border-primary/30 hover:shadow-sm transition-all focus-ring"
              aria-label={`信任中心，已完成${verifiedCount}项认证`}
            >
              <div className="flex items-center gap-3 mb-3">
                <ProgressRing progress={verificationProgress} size={48} strokeWidth={4} color="rose">
                  <Shield className="w-5 h-5 text-primary" />
                </ProgressRing>
                <div className="flex-1">
                  <h3 className="font-medium">信任中心</h3>
                  <p className="text-xs text-muted-foreground">
                    {verifiedCount}/{verificationItems.length} 项已认证
                  </p>
                </div>
                <ChevronRight className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
              </div>
              <div className="grid grid-cols-4 gap-2">
                {verificationItems.map((item, i) => (
                  <div
                    key={i}
                    className={cn(
                      'text-center p-2 rounded-lg transition-colors',
                      item.status === 'verified'
                        ? 'bg-primary/10'
                        : item.status === 'pending'
                          ? 'bg-gold/10'
                          : 'bg-secondary',
                    )}
                  >
                    <div className="flex justify-center mb-1">{getStatusIcon(item.status)}</div>
                    <span className="text-[10px] text-muted-foreground">{item.name}</span>
                  </div>
                ))}
              </div>
            </button>
          </section>
        </FadeIn>

        <FadeIn delay={300}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-medium text-sm">理想类型</h3>
              <button type="button" className="text-xs text-primary hover:underline focus-ring rounded">
                编辑
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(preferences).map(([key, value]) => (
                <div key={key} className="bg-secondary rounded-lg px-3 py-2">
                  <span className="text-[10px] text-muted-foreground block">
                    {key === 'ageRange'
                      ? '年龄'
                      : key === 'location'
                        ? '城市'
                        : key === 'education'
                          ? '学历'
                          : '身高'}
                  </span>
                  <span className="text-sm">{value}</span>
                </div>
              ))}
            </div>
          </section>
        </FadeIn>

        <FadeIn delay={400}>
          <section className="bg-card border border-border rounded-xl overflow-hidden">
            {menuItems.map((item, i) => {
              const Icon = item.icon
              return (
                <button
                  key={i}
                  type="button"
                  className={cn(
                    'w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/50 transition-colors focus-ring',
                    i !== menuItems.length - 1 && 'border-b border-border',
                  )}
                  aria-label={item.label}
                >
                  <Icon className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
                  <span className="flex-1 text-sm">{item.label}</span>
                  {item.badge && <span className="text-xs text-muted-foreground">{item.badge}</span>}
                  <ChevronRight className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                </button>
              )
            })}
          </section>
        </FadeIn>

        <p className="text-center text-xs text-muted-foreground pt-4">Her</p>
      </div>
    </PageTransition>
  )
}
