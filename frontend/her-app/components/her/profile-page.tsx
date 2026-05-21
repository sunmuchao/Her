'use client'

import { Settings, ChevronRight, BadgeCheck, Heart, MapPin, Briefcase, GraduationCap, Edit3, Shield, Bell, HelpCircle, CheckCircle, Clock, XCircle } from 'lucide-react'
import Image from 'next/image'
import { cn } from '@/lib/utils'
import { ProgressRing } from './ui/progress-ring'
import { FadeIn, PageTransition } from './ui/animations'
import { ThemeToggle } from './ui/theme-toggle'

interface ProfilePageProps {
  onStartVerification: () => void
  onOpenTrustCenter?: () => void
}

const userProfile = {
  name: '苏晴',
  age: 26,
  city: '上海',
  avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200&h=200&fit=crop&crop=face',
  headline: '相信美好，期待遇见',
  verified: true,
  occupation: '市场经理',
  education: '上海交通大学 · 硕士',
  relationshipGoal: '认真恋爱，期待结婚',
}

const personalityTags = ['温柔', '独立', '爱阅读', '咖啡控', '旅行爱好者']

const preferences = {
  ageRange: '26-32岁',
  location: '上海优先',
  education: '本科及以上',
  height: '175cm以上',
}

const verificationItems = [
  { name: '身份', status: 'verified' },
  { name: '学历', status: 'verified' },
  { name: '职业', status: 'pending' },
  { name: '收入', status: 'unverified' },
]

const menuItems = [
  { icon: Edit3, label: '编辑资料' },
  { icon: Heart, label: '理想类型', badge: '已设置' },
  { icon: Bell, label: '通知设置' },
  { icon: HelpCircle, label: '帮助中心' },
]

export default function ProfilePage({ onStartVerification, onOpenTrustCenter }: ProfilePageProps) {
  const getStatusIcon = (status: string) => {
    if (status === 'verified') return <CheckCircle className="w-4 h-4 text-primary" />
    if (status === 'pending') return <Clock className="w-4 h-4 text-gold" />
    return <XCircle className="w-4 h-4 text-muted-foreground" />
  }

  const verifiedCount = verificationItems.filter(i => i.status === 'verified').length
  const verificationProgress = (verifiedCount / verificationItems.length) * 100

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-medium">我的</h1>
          <div className="flex items-center gap-2">
            <ThemeToggle size="sm" />
            <button className="w-8 h-8 flex items-center justify-center focus-ring rounded-full" aria-label="设置">
              <Settings className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {/* Profile card */}
        <FadeIn delay={100}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="relative">
                <div className="w-16 h-16 rounded-full overflow-hidden">
                  <Image src={userProfile.avatar} alt={userProfile.name} width={64} height={64} className="object-cover" />
                </div>
                {userProfile.verified && (
                  <BadgeCheck className="absolute -bottom-0.5 -right-0.5 w-5 h-5 text-primary bg-background rounded-full" aria-label="已认证" />
                )}
              </div>
              <div>
                <h2 className="font-medium">{userProfile.name}，{userProfile.age}</h2>
                <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                  <span className="flex items-center gap-1"><MapPin className="w-3 h-3" aria-hidden="true" />{userProfile.city}</span>
                  <span>{userProfile.occupation}</span>
                </div>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mb-3">{userProfile.headline}</p>
            <div className="flex flex-wrap gap-1.5">
              {personalityTags.map((tag, i) => (
                <span key={i} className="px-2 py-1 bg-secondary text-xs text-muted-foreground rounded-md animate-scale-in" style={{ animationDelay: `${i * 30}ms` }}>{tag}</span>
              ))}
            </div>
          </section>
        </FadeIn>

        {/* Trust Center with Progress Ring */}
        <FadeIn delay={200}>
          <section>
            <button
              onClick={onOpenTrustCenter || onStartVerification}
              className="w-full bg-card border border-border rounded-xl p-4 text-left hover:border-primary/30 hover:shadow-sm transition-all focus-ring"
              aria-label={`认证中心，已完成${verifiedCount}项认证`}
            >
              <div className="flex items-center gap-3 mb-3">
                <ProgressRing progress={verificationProgress} size={48} strokeWidth={4} color="rose">
                  <Shield className="w-5 h-5 text-primary" />
                </ProgressRing>
                <div className="flex-1">
                  <h3 className="font-medium">认证中心</h3>
                  <p className="text-xs text-muted-foreground">{verifiedCount}/{verificationItems.length} 项已认证</p>
                </div>
                <ChevronRight className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
              </div>
              <div className="grid grid-cols-4 gap-2">
                {verificationItems.map((item, i) => (
                  <div key={i} className={cn(
                    'text-center p-2 rounded-lg transition-colors',
                    item.status === 'verified' ? 'bg-primary/10' :
                    item.status === 'pending' ? 'bg-gold/10' : 'bg-secondary'
                  )}>
                    <div className="flex justify-center mb-1">{getStatusIcon(item.status)}</div>
                    <span className="text-[10px] text-muted-foreground">{item.name}</span>
                  </div>
                ))}
              </div>
            </button>
          </section>
        </FadeIn>

        {/* Preferences */}
        <FadeIn delay={300}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-medium text-sm">理想类型</h3>
              <button className="text-xs text-primary hover:underline focus-ring rounded">编辑</button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(preferences).map(([key, value]) => (
                <div key={key} className="bg-secondary rounded-lg px-3 py-2">
                  <span className="text-[10px] text-muted-foreground block">{
                    key === 'ageRange' ? '年龄' : key === 'location' ? '城市' : key === 'education' ? '学历' : '身高'
                  }</span>
                  <span className="text-sm">{value}</span>
                </div>
              ))}
            </div>
          </section>
        </FadeIn>

        {/* Menu */}
        <FadeIn delay={400}>
          <section className="bg-card border border-border rounded-xl overflow-hidden">
            {menuItems.map((item, i) => {
              const Icon = item.icon
              return (
                <button
                  key={i}
                  className={cn(
                    'w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/50 transition-colors focus-ring',
                    i !== menuItems.length - 1 && 'border-b border-border'
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

        <p className="text-center text-xs text-muted-foreground pt-4">Her v1.0.0</p>
      </div>
    </PageTransition>
  )
}
