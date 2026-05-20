'use client'

import { Settings, ChevronRight, BadgeCheck, Heart, Target, User, MapPin, Briefcase, GraduationCap, Edit3, Shield, Bell, HelpCircle } from 'lucide-react'
import Image from 'next/image'

interface ProfilePageProps {
  onStartVerification: () => void
}

const userProfile = {
  name: '苏晴',
  age: 26,
  city: '上海',
  avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200&h=200&fit=crop&crop=face',
  headline: '相信美好，期待遇见',
  verified: true,
  verificationLevel: '已认证',
  occupation: '市场经理',
  education: '上海交通大学 · 硕士',
  relationshipGoal: '认真恋爱，期待结婚',
}

const personalityTags = [
  '温柔', '独立', '爱阅读', '咖啡控', '旅行爱好者', '猫奴'
]

const preferences = {
  ageRange: '26-32岁',
  location: '上海优先',
  education: '本科及以上',
  height: '175cm以上',
}

const menuItems = [
  {
    group: '我的资料',
    items: [
      { icon: Edit3, label: '编辑资料', badge: null },
      { icon: Target, label: '恋爱目标', badge: null },
      { icon: Heart, label: '理想类型', badge: '已设置' },
    ]
  },
  {
    group: '信任与安全',
    items: [
      { icon: Shield, label: '认证中心', badge: '3项已认证', highlight: true },
      { icon: Bell, label: '通知设置', badge: null },
    ]
  },
  {
    group: '帮助与支持',
    items: [
      { icon: HelpCircle, label: '帮助中心', badge: null },
    ]
  },
]

export default function ProfilePage({ onStartVerification }: ProfilePageProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-5 py-4 flex items-center justify-between">
            <h1 className="editorial-title text-2xl text-foreground">我的</h1>
            <button className="w-10 h-10 rounded-full bg-secondary/60 flex items-center justify-center hover:bg-secondary transition-colors">
              <Settings className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {/* Profile card */}
        <section className="bg-gradient-to-br from-card via-card to-rose-soft/30 rounded-3xl overflow-hidden shadow-soft border border-rose-soft/30">
          {/* Cover gradient */}
          <div className="h-20 bg-gradient-to-r from-rose-soft/60 via-blush to-gold-soft/40" />
          
          {/* Profile info */}
          <div className="px-5 pb-5 -mt-10">
            <div className="flex items-end gap-4 mb-4">
              <div className="relative">
                <div className="w-20 h-20 rounded-full overflow-hidden border-4 border-card shadow-soft">
                  <Image
                    src={userProfile.avatar}
                    alt={userProfile.name}
                    width={80}
                    height={80}
                    className="object-cover"
                  />
                </div>
                {userProfile.verified && (
                  <div className="absolute -bottom-1 -right-1 w-7 h-7 bg-card rounded-full flex items-center justify-center shadow-soft">
                    <BadgeCheck className="w-5 h-5 text-primary" />
                  </div>
                )}
              </div>
              <div className="flex-1 pb-1">
                <h2 className="text-xl font-medium text-foreground">{userProfile.name}，{userProfile.age}</h2>
                <p className="text-xs text-muted-foreground">{userProfile.verificationLevel}</p>
              </div>
            </div>

            <p className="editorial-title text-lg text-foreground/80 mb-4">{userProfile.headline}</p>

            {/* Basic info */}
            <div className="flex flex-wrap gap-3 text-sm text-muted-foreground mb-4">
              <span className="flex items-center gap-1">
                <MapPin className="w-4 h-4" />
                {userProfile.city}
              </span>
              <span className="flex items-center gap-1">
                <Briefcase className="w-4 h-4" />
                {userProfile.occupation}
              </span>
              <span className="flex items-center gap-1">
                <GraduationCap className="w-4 h-4" />
                {userProfile.education}
              </span>
            </div>

            {/* Relationship goal */}
            <div className="bg-rose-soft/40 rounded-xl px-4 py-3 mb-4">
              <div className="flex items-center gap-2">
                <Heart className="w-4 h-4 text-primary" />
                <span className="text-sm font-medium text-foreground">{userProfile.relationshipGoal}</span>
              </div>
            </div>

            {/* Personality tags */}
            <div className="flex flex-wrap gap-2">
              {personalityTags.map((tag, index) => (
                <span
                  key={index}
                  className="px-3 py-1.5 bg-blush/60 text-taupe text-xs rounded-full border border-rose-soft/50"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* Preferences summary */}
        <section className="bg-card rounded-2xl p-4 shadow-soft border border-border/50">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-foreground">理想类型偏好</h3>
            <button className="text-xs text-primary">编辑</button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-secondary/40 rounded-xl px-3 py-2">
              <span className="text-[10px] text-muted-foreground">年龄</span>
              <p className="text-sm text-foreground">{preferences.ageRange}</p>
            </div>
            <div className="bg-secondary/40 rounded-xl px-3 py-2">
              <span className="text-[10px] text-muted-foreground">城市</span>
              <p className="text-sm text-foreground">{preferences.location}</p>
            </div>
            <div className="bg-secondary/40 rounded-xl px-3 py-2">
              <span className="text-[10px] text-muted-foreground">学历</span>
              <p className="text-sm text-foreground">{preferences.education}</p>
            </div>
            <div className="bg-secondary/40 rounded-xl px-3 py-2">
              <span className="text-[10px] text-muted-foreground">身高</span>
              <p className="text-sm text-foreground">{preferences.height}</p>
            </div>
          </div>
        </section>

        {/* Menu groups */}
        {menuItems.map((group, groupIndex) => (
          <section key={groupIndex}>
            <h3 className="text-xs text-muted-foreground mb-2 px-1">{group.group}</h3>
            <div className="bg-card rounded-2xl shadow-soft border border-border/50 overflow-hidden">
              {group.items.map((item, itemIndex) => {
                const Icon = item.icon
                return (
                  <button
                    key={itemIndex}
                    onClick={item.label === '认证中心' ? onStartVerification : undefined}
                    className={`w-full px-4 py-3.5 flex items-center gap-3 text-left transition-colors hover:bg-secondary/30 ${
                      itemIndex !== group.items.length - 1 ? 'border-b border-border/30' : ''
                    }`}
                  >
                    <div className={`w-9 h-9 rounded-full flex items-center justify-center ${
                      item.highlight ? 'bg-rose-soft/50' : 'bg-secondary/60'
                    }`}>
                      <Icon className={`w-4.5 h-4.5 ${item.highlight ? 'text-primary' : 'text-muted-foreground'}`} />
                    </div>
                    <span className="flex-1 text-sm text-foreground">{item.label}</span>
                    {item.badge && (
                      <span className={`text-xs ${item.highlight ? 'text-primary' : 'text-muted-foreground'}`}>
                        {item.badge}
                      </span>
                    )}
                    <ChevronRight className="w-5 h-5 text-muted-foreground/50" />
                  </button>
                )
              })}
            </div>
          </section>
        ))}

        {/* App info */}
        <div className="text-center py-4">
          <p className="text-xs text-muted-foreground/60">Her v1.0.0</p>
        </div>
      </div>
    </div>
  )
}
