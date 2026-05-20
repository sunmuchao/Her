'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Calendar, Heart, Tag, Sliders } from 'lucide-react'

interface OnboardingPageProps {
  onComplete: () => void
  onBack: () => void
}

type Step = 'basics' | 'goals' | 'tags' | 'preferences'

interface ProfileData {
  name: string
  birthday: string
  gender: string
  location: string
  relationshipGoal: string
  tags: string[]
  ageRange: [number, number]
  locationPref: string
}

const AVAILABLE_TAGS = [
  '爱读书', '热爱旅行', '美食家', '健身达人', '电影迷', 
  '音乐爱好者', '猫奴', '狗派', '咖啡控', '喜欢户外',
  '追剧', '摄影', '瑜伽', '烘焙', '画画',
  '独立', '温柔', '幽默', '有上进心', '善于倾听',
]

export default function OnboardingPage({ 
  onComplete,
  onBack 
}: OnboardingPageProps) {
  const [currentStep, setCurrentStep] = useState<Step>('basics')
  const [profile, setProfile] = useState<ProfileData>({
    name: '',
    birthday: '',
    gender: '',
    location: '',
    relationshipGoal: '',
    tags: [],
    ageRange: [25, 35],
    locationPref: '',
  })

  const steps: Step[] = ['basics', 'goals', 'tags', 'preferences']
  const currentIndex = steps.indexOf(currentStep)
  const progress = ((currentIndex + 1) / steps.length) * 100

  const handleNext = () => {
    const nextIndex = currentIndex + 1
    if (nextIndex < steps.length) {
      setCurrentStep(steps[nextIndex])
    } else {
      onComplete()
    }
  }

  const handlePrev = () => {
    if (currentIndex === 0) {
      onBack()
    } else {
      setCurrentStep(steps[currentIndex - 1])
    }
  }

  const canProceed = () => {
    switch (currentStep) {
      case 'basics':
        return profile.name && profile.birthday && profile.gender && profile.location
      case 'goals':
        return profile.relationshipGoal
      case 'tags':
        return profile.tags.length >= 3
      case 'preferences':
        return true
      default:
        return false
    }
  }

  const toggleTag = (tag: string) => {
    setProfile(prev => ({
      ...prev,
      tags: prev.tags.includes(tag)
        ? prev.tags.filter(t => t !== tag)
        : prev.tags.length < 8
          ? [...prev.tags, tag]
          : prev.tags
    }))
  }

  const stepConfig = {
    basics: { icon: Calendar, title: '基本信息', subtitle: '让我先认识你' },
    goals: { icon: Heart, title: '恋爱期待', subtitle: '你在寻找什么样的关系' },
    tags: { icon: Tag, title: '个人标签', subtitle: '让别人更快了解你' },
    preferences: { icon: Sliders, title: '偏好设置', subtitle: '告诉我你期待的 TA' },
  }

  const config = stepConfig[currentStep]
  const StepIcon = config.icon

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/20 via-background to-background" />
        <div className="grain-texture absolute inset-0" />
      </div>

      {/* Header */}
      <header className="relative z-10 px-4 pt-14 pb-4">
        <div className="flex items-center justify-between mb-4">
          <button 
            onClick={handlePrev}
            className="w-10 h-10 rounded-full flex items-center justify-center transition-colors"
            style={{ background: 'oklch(0.95 0.01 80)' }}
          >
            <ChevronLeft className="w-5 h-5" style={{ color: 'oklch(0.4 0.03 30)' }} />
          </button>
          
          <span className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
            {currentIndex + 1} / {steps.length}
          </span>
        </div>

        {/* Progress bar */}
        <div 
          className="h-1 rounded-full overflow-hidden"
          style={{ background: 'oklch(0.92 0.02 80)' }}
        >
          <div 
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{ 
              width: `${progress}%`,
              background: 'linear-gradient(90deg, oklch(0.65 0.1 15), oklch(0.55 0.12 15))',
            }}
          />
        </div>
      </header>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col px-8 pt-4">
        
        {/* Step header */}
        <div className="flex items-center gap-4 mb-8">
          <div 
            className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, oklch(0.95 0.04 15 / 0.8), oklch(0.92 0.05 80 / 0.5))',
              boxShadow: '0 4px 16px oklch(0.55 0.12 15 / 0.1)',
            }}
          >
            <StepIcon className="w-6 h-6" style={{ color: 'oklch(0.55 0.12 15)' }} />
          </div>
          <div>
            <h1 
              className="editorial-title text-2xl mb-1"
              style={{ color: 'oklch(0.3 0.03 25)' }}
            >
              {config.title}
            </h1>
            <p className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
              {config.subtitle}
            </p>
          </div>
        </div>

        {/* Step content */}
        <div className="flex-1">
          {currentStep === 'basics' && (
            <div className="space-y-5">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: 'oklch(0.4 0.03 30)' }}>
                  你的名字
                </label>
                <input
                  type="text"
                  value={profile.name}
                  onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                  placeholder="怎么称呼你"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all"
                  style={{
                    background: 'oklch(0.97 0.008 80)',
                    border: '2px solid oklch(0.9 0.02 80)',
                    color: 'oklch(0.3 0.03 25)',
                  }}
                />
              </div>

              {/* Birthday */}
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: 'oklch(0.4 0.03 30)' }}>
                  生日
                </label>
                <input
                  type="date"
                  value={profile.birthday}
                  onChange={(e) => setProfile({ ...profile, birthday: e.target.value })}
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all"
                  style={{
                    background: 'oklch(0.97 0.008 80)',
                    border: '2px solid oklch(0.9 0.02 80)',
                    color: profile.birthday ? 'oklch(0.3 0.03 25)' : 'oklch(0.6 0.02 30)',
                  }}
                />
              </div>

              {/* Gender */}
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: 'oklch(0.4 0.03 30)' }}>
                  性别
                </label>
                <div className="flex gap-3">
                  {[
                    { value: 'female', label: '女生' },
                    { value: 'male', label: '男生' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setProfile({ ...profile, gender: option.value })}
                      className="flex-1 py-3.5 rounded-xl text-sm font-medium transition-all"
                      style={{
                        background: profile.gender === option.value 
                          ? 'linear-gradient(135deg, oklch(0.92 0.06 15), oklch(0.88 0.08 15))'
                          : 'oklch(0.97 0.008 80)',
                        border: `2px solid ${profile.gender === option.value ? 'oklch(0.7 0.1 15)' : 'oklch(0.9 0.02 80)'}`,
                        color: profile.gender === option.value ? 'oklch(0.45 0.1 15)' : 'oklch(0.5 0.03 30)',
                      }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Location */}
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: 'oklch(0.4 0.03 30)' }}>
                  所在城市
                </label>
                <input
                  type="text"
                  value={profile.location}
                  onChange={(e) => setProfile({ ...profile, location: e.target.value })}
                  placeholder="你现在住在哪里"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all"
                  style={{
                    background: 'oklch(0.97 0.008 80)',
                    border: '2px solid oklch(0.9 0.02 80)',
                    color: 'oklch(0.3 0.03 25)',
                  }}
                />
              </div>
            </div>
          )}

          {currentStep === 'goals' && (
            <div className="space-y-3">
              {[
                { value: 'serious', label: '认真寻找长期伴侣', desc: '想找一个能一起走下去的人' },
                { value: 'explore', label: '慢慢了解，随缘发展', desc: '先从朋友开始，看看感觉' },
                { value: 'marriage', label: '以结婚为目标', desc: '目标明确，希望尽快步入婚姻' },
              ].map((option) => (
                <button
                  key={option.value}
                  onClick={() => setProfile({ ...profile, relationshipGoal: option.value })}
                  className="w-full p-5 rounded-2xl text-left transition-all"
                  style={{
                    background: profile.relationshipGoal === option.value 
                      ? 'linear-gradient(135deg, oklch(0.96 0.04 15), oklch(0.92 0.05 80 / 0.5))'
                      : 'oklch(0.98 0.008 80)',
                    border: `2px solid ${profile.relationshipGoal === option.value ? 'oklch(0.7 0.1 15)' : 'oklch(0.9 0.02 80)'}`,
                    boxShadow: profile.relationshipGoal === option.value ? '0 4px 16px oklch(0.55 0.12 15 / 0.1)' : 'none',
                  }}
                >
                  <div 
                    className="font-medium mb-1"
                    style={{ color: profile.relationshipGoal === option.value ? 'oklch(0.4 0.08 15)' : 'oklch(0.35 0.03 30)' }}
                  >
                    {option.label}
                  </div>
                  <div 
                    className="text-sm"
                    style={{ color: 'oklch(0.55 0.02 30)' }}
                  >
                    {option.desc}
                  </div>
                </button>
              ))}
            </div>
          )}

          {currentStep === 'tags' && (
            <div>
              <p 
                className="text-sm mb-5"
                style={{ color: 'oklch(0.55 0.02 30)' }}
              >
                选择 3-8 个最能代表你的标签
                <span className="ml-2" style={{ color: 'oklch(0.6 0.08 15)' }}>
                  ({profile.tags.length}/8)
                </span>
              </p>
              
              <div className="flex flex-wrap gap-2.5">
                {AVAILABLE_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className="px-4 py-2.5 rounded-full text-sm font-medium transition-all"
                    style={{
                      background: profile.tags.includes(tag) 
                        ? 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))'
                        : 'oklch(0.97 0.01 80)',
                      border: `1.5px solid ${profile.tags.includes(tag) ? 'transparent' : 'oklch(0.88 0.02 80)'}`,
                      color: profile.tags.includes(tag) ? 'oklch(0.98 0.005 85)' : 'oklch(0.45 0.03 30)',
                      boxShadow: profile.tags.includes(tag) ? '0 2px 8px oklch(0.55 0.12 15 / 0.25)' : 'none',
                    }}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          )}

          {currentStep === 'preferences' && (
            <div className="space-y-8">
              {/* Age range */}
              <div>
                <label className="block text-sm font-medium mb-4" style={{ color: 'oklch(0.4 0.03 30)' }}>
                  期望 TA 的年龄范围
                </label>
                <div 
                  className="text-center py-4 rounded-xl mb-4"
                  style={{ background: 'oklch(0.96 0.02 15 / 0.3)' }}
                >
                  <span 
                    className="text-2xl font-medium"
                    style={{ color: 'oklch(0.45 0.1 15)' }}
                  >
                    {profile.ageRange[0]} - {profile.ageRange[1]} 岁
                  </span>
                </div>
                <div className="flex gap-4">
                  <div className="flex-1">
                    <span className="block text-xs mb-2" style={{ color: 'oklch(0.55 0.02 30)' }}>最小年龄</span>
                    <input
                      type="range"
                      min="18"
                      max="60"
                      value={profile.ageRange[0]}
                      onChange={(e) => setProfile({
                        ...profile,
                        ageRange: [Math.min(Number(e.target.value), profile.ageRange[1] - 1), profile.ageRange[1]]
                      })}
                      className="w-full accent-rose"
                    />
                  </div>
                  <div className="flex-1">
                    <span className="block text-xs mb-2" style={{ color: 'oklch(0.55 0.02 30)' }}>最大年龄</span>
                    <input
                      type="range"
                      min="18"
                      max="60"
                      value={profile.ageRange[1]}
                      onChange={(e) => setProfile({
                        ...profile,
                        ageRange: [profile.ageRange[0], Math.max(Number(e.target.value), profile.ageRange[0] + 1)]
                      })}
                      className="w-full accent-rose"
                    />
                  </div>
                </div>
              </div>

              {/* Location preference */}
              <div>
                <label className="block text-sm font-medium mb-3" style={{ color: 'oklch(0.4 0.03 30)' }}>
                  期望 TA 的位置
                </label>
                <div className="space-y-2">
                  {[
                    { value: 'same_city', label: '同城' },
                    { value: 'nearby', label: '附近城市也可以' },
                    { value: 'any', label: '不限制' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setProfile({ ...profile, locationPref: option.value })}
                      className="w-full py-3.5 px-4 rounded-xl text-sm font-medium text-left transition-all"
                      style={{
                        background: profile.locationPref === option.value 
                          ? 'linear-gradient(135deg, oklch(0.92 0.06 15), oklch(0.88 0.08 15))'
                          : 'oklch(0.97 0.008 80)',
                        border: `2px solid ${profile.locationPref === option.value ? 'oklch(0.7 0.1 15)' : 'oklch(0.9 0.02 80)'}`,
                        color: profile.locationPref === option.value ? 'oklch(0.45 0.1 15)' : 'oklch(0.5 0.03 30)',
                      }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* CTA Button */}
        <div className="py-8 safe-area-bottom">
          <button
            onClick={handleNext}
            disabled={!canProceed()}
            className="w-full py-4 rounded-2xl font-medium text-base transition-all duration-300 active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-2"
            style={{
              background: canProceed()
                ? 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))'
                : 'oklch(0.9 0.02 80)',
              color: canProceed() ? 'oklch(0.98 0.005 85)' : 'oklch(0.6 0.02 30)',
              boxShadow: canProceed() ? '0 4px 20px oklch(0.55 0.12 15 / 0.3)' : 'none',
            }}
          >
            {currentIndex === steps.length - 1 ? '完成' : '下一步'}
            {currentIndex < steps.length - 1 && <ChevronRight className="w-5 h-5" />}
          </button>
        </div>
      </div>
    </div>
  )
}
