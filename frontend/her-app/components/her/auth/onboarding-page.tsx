'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Calendar, Heart, Tag, Sliders } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CustomRangeSlider } from '@/components/her/ui/custom-range-slider'

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
            className="w-10 h-10 rounded-full flex items-center justify-center transition-colors bg-secondary hover:bg-secondary/80 focus-ring"
            aria-label={currentIndex === 0 ? '返回' : '上一步'}
          >
            <ChevronLeft className="w-5 h-5 text-foreground" />
          </button>
          
          <span className="text-sm text-muted-foreground" aria-live="polite">
            {currentIndex + 1} / {steps.length}
          </span>
        </div>

        {/* Progress bar */}
        <div 
          className="h-1.5 rounded-full overflow-hidden bg-secondary"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div 
            className="h-full rounded-full transition-all duration-500 ease-out bg-gradient-to-r from-rose to-primary"
            style={{ width: `${progress}%` }}
          />
        </div>
      </header>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col px-8 pt-4">
        
        {/* Step header */}
        <div className="flex items-center gap-4 mb-8 animate-fade-in-up">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center bg-gradient-to-br from-rose-soft to-gold-soft shadow-sm">
            <StepIcon className="w-6 h-6 text-primary" aria-hidden="true" />
          </div>
          <div>
            <h1 className="editorial-title text-2xl mb-1 text-foreground">
              {config.title}
            </h1>
            <p className="text-sm text-muted-foreground">
              {config.subtitle}
            </p>
          </div>
        </div>

        {/* Step content */}
        <div className="flex-1 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
          {currentStep === 'basics' && (
            <div className="space-y-5">
              {/* Name */}
              <div>
                <label htmlFor="name" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  你的名字
                </label>
                <input
                  id="name"
                  type="text"
                  value={profile.name}
                  onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                  placeholder="怎么称呼你"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Birthday */}
              <div>
                <label htmlFor="birthday" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  生日
                </label>
                <input
                  id="birthday"
                  type="date"
                  value={profile.birthday}
                  onChange={(e) => setProfile({ ...profile, birthday: e.target.value })}
                  className={cn(
                    'w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border focus:border-primary focus:ring-1 focus:ring-primary',
                    profile.birthday ? 'text-foreground' : 'text-muted-foreground'
                  )}
                />
              </div>

              {/* Gender */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  性别
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'female', label: '女生' },
                    { value: 'male', label: '男生' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, gender: option.value })}
                      className={cn(
                        'flex-1 py-3.5 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.gender === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.gender === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Location */}
              <div>
                <label htmlFor="location" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  所在城市
                </label>
                <input
                  id="location"
                  type="text"
                  value={profile.location}
                  onChange={(e) => setProfile({ ...profile, location: e.target.value })}
                  placeholder="你现在住在哪里"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>
          )}

          {currentStep === 'goals' && (
            <fieldset className="space-y-3">
              <legend className="sr-only">选择你的恋爱期待</legend>
              {[
                { value: 'serious', label: '认真寻找长期伴侣', desc: '想找一个能一起走下去的人' },
                { value: 'explore', label: '慢慢了解，随缘发展', desc: '先从朋友开始，看看感觉' },
                { value: 'marriage', label: '以结婚为目标', desc: '目标明确，希望尽快步入婚姻' },
              ].map((option, index) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setProfile({ ...profile, relationshipGoal: option.value })}
                  className={cn(
                    'w-full p-5 rounded-2xl text-left transition-all border-2 focus-ring animate-fade-in-up',
                    profile.relationshipGoal === option.value 
                      ? 'bg-gradient-to-br from-rose-soft to-gold-soft/50 border-rose shadow-sm'
                      : 'bg-card border-border hover:border-border/80'
                  )}
                  style={{ animationDelay: `${index * 50}ms` }}
                  aria-pressed={profile.relationshipGoal === option.value}
                >
                  <div className={cn(
                    'font-medium mb-1',
                    profile.relationshipGoal === option.value ? 'text-primary' : 'text-foreground'
                  )}>
                    {option.label}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {option.desc}
                  </div>
                </button>
              ))}
            </fieldset>
          )}

          {currentStep === 'tags' && (
            <div>
              <p className="text-sm mb-5 text-muted-foreground">
                选择 3-8 个最能代表你的标签
                <span className="ml-2 text-rose font-medium">
                  ({profile.tags.length}/8)
                </span>
              </p>
              
              <div className="flex flex-wrap gap-2.5" role="group" aria-label="个人标签选择">
                {AVAILABLE_TAGS.map((tag, index) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    className={cn(
                      'px-4 py-2.5 rounded-full text-sm font-medium transition-all border animate-scale-in focus-ring',
                      profile.tags.includes(tag) 
                        ? 'bg-primary text-primary-foreground border-transparent shadow-md shadow-primary/20'
                        : 'bg-card border-border text-secondary-foreground hover:border-primary/30'
                    )}
                    style={{ animationDelay: `${index * 20}ms` }}
                    aria-pressed={profile.tags.includes(tag)}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          )}

          {currentStep === 'preferences' && (
            <div className="space-y-8">
              {/* Age range with custom slider */}
              <div>
                <label className="block text-sm font-medium mb-4 text-secondary-foreground">
                  期望 TA 的年龄范围
                </label>
                <CustomRangeSlider
                  min={18}
                  max={60}
                  value={profile.ageRange}
                  onChange={(value) => setProfile({ ...profile, ageRange: value })}
                  formatLabel={(v) => `${v}岁`}
                />
              </div>

              {/* Location preference */}
              <fieldset>
                <legend className="block text-sm font-medium mb-3 text-secondary-foreground">
                  期望 TA 的位置
                </legend>
                <div className="space-y-2">
                  {[
                    { value: 'same_city', label: '同城' },
                    { value: 'nearby', label: '附近城市也可以' },
                    { value: 'any', label: '不限制' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, locationPref: option.value })}
                      className={cn(
                        'w-full py-3.5 px-4 rounded-xl text-sm font-medium text-left transition-all border-2 focus-ring',
                        profile.locationPref === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.locationPref === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          )}
        </div>

        {/* CTA Button */}
        <div className="py-8 safe-area-bottom">
          <button
            onClick={handleNext}
            disabled={!canProceed()}
            className={cn(
              'w-full py-4 rounded-2xl font-medium text-base transition-all duration-300 active:scale-[0.98] flex items-center justify-center gap-2 focus-ring',
              canProceed()
                ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/30 hover:shadow-xl hover:shadow-primary/40'
                : 'bg-secondary text-muted-foreground cursor-not-allowed'
            )}
          >
            {currentIndex === steps.length - 1 ? '完成' : '下一步'}
            {currentIndex < steps.length - 1 && <ChevronRight className="w-5 h-5" aria-hidden="true" />}
          </button>
        </div>
      </div>
    </div>
  )
}
