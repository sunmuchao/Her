'use client'

import { useState, useRef, useEffect, useCallback, type TouchEvent } from 'react'
import { ChevronLeft, ChevronRight, Calendar, Heart, Tag, Sliders, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { applyLoginPayload } from '@/lib/auth/session'
import { notifyError, notifySuccess } from '@/lib/notify'
import { Button } from '@/components/ui/button'
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
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [direction, setDirection] = useState<'forward' | 'backward'>('forward')
  const [isTransitioning, setIsTransitioning] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const touchStartX = useRef(0)
  const touchEndX = useRef(0)
  
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

  // Smooth step transition
  const transitionToStep = useCallback((newStep: Step, dir: 'forward' | 'backward') => {
    setDirection(dir)
    setIsTransitioning(true)
    
    // Short delay for exit animation
    setTimeout(() => {
      setCurrentStep(newStep)
      // Reset transition state after enter animation
      setTimeout(() => setIsTransitioning(false), 50)
    }, 150)
  }, [])

  // Handle swipe gestures
  const handleTouchStart = (e: TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
  }

  const handleTouchMove = (e: TouchEvent) => {
    touchEndX.current = e.touches[0].clientX
  }

  const handleTouchEnd = () => {
    const swipeThreshold = 80
    const diff = touchStartX.current - touchEndX.current

    if (Math.abs(diff) > swipeThreshold) {
      if (diff > 0 && canProceed() && currentIndex < steps.length - 1) {
        // Swipe left - next step
        transitionToStep(steps[currentIndex + 1], 'forward')
      } else if (diff < 0 && currentIndex > 0) {
        // Swipe right - previous step
        transitionToStep(steps[currentIndex - 1], 'backward')
      }
    }
    touchStartX.current = 0
    touchEndX.current = 0
  }

  // Auto-scroll content into view when step changes
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [currentStep])

  const handleNext = async () => {
    const nextIndex = currentIndex + 1
    if (nextIndex < steps.length) {
      transitionToStep(steps[nextIndex], 'forward')
      return
    }
    setIsSubmitting(true)
    try {
      const result = await submitOnboarding({
        basic_info: {
          name: profile.name,
          birthday: profile.birthday,
          gender: profile.gender,
          location: profile.location,
          relationship_goal: profile.relationshipGoal,
        },
        preference: {
          relationship_goal: profile.relationshipGoal,
          tags: profile.tags,
          age_range: profile.ageRange,
          location_pref: profile.locationPref,
        },
        mark_completed: true,
      })
      applyLoginPayload({
        user: {
          user_id: result.user?.user_id,
          onboarding_status: result.user?.onboarding_status,
          profile_id: result.profile_id,
          requester_id: result.requester_id,
        },
        onboarding: {
          profile_id: result.profile_id,
        },
      })
      notifySuccess('资料已保存到用户画像库')
      onComplete()
    } catch (error) {
      notifyError(error, '资料保存失败，请重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handlePrev = () => {
    if (currentIndex === 0) {
      onBack()
    } else {
      transitionToStep(steps[currentIndex - 1], 'backward')
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
          className="h-1 rounded-full overflow-hidden bg-secondary"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div 
            className="h-full rounded-full bg-gradient-to-r from-rose to-primary"
            style={{ 
              width: `${progress}%`,
              transition: 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1)'
            }}
          />
        </div>
      </header>

      {/* Content with touch gestures */}
      <div 
        ref={contentRef}
        className="relative z-10 flex-1 flex flex-col px-8 pt-4 overflow-y-auto scrollbar-hide"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        
        {/* Step header with smooth transition */}
        <div 
          className={cn(
            'flex items-center gap-4 mb-8 transition-all duration-300',
            isTransitioning ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'
          )}
        >
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

        {/* Step content with smooth transitions */}
        <div 
          className={cn(
            'flex-1 transition-all duration-300 ease-out',
            isTransitioning 
              ? direction === 'forward' 
                ? 'opacity-0 translate-x-8' 
                : 'opacity-0 -translate-x-8'
              : 'opacity-100 translate-x-0'
          )}
        >
          {currentStep === 'basics' && (
            <div className="space-y-5">
              {/* Name */}
              <div className="animate-fade-in-up" style={{ animationDelay: '0ms' }}>
                <label htmlFor="name" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  你的名字
                </label>
                <input
                  id="name"
                  type="text"
                  value={profile.name}
                  onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                  placeholder="怎么称呼你"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all duration-200 bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-background"
                  autoComplete="name"
                />
              </div>

              {/* Birthday */}
              <div className="animate-fade-in-up" style={{ animationDelay: '50ms' }}>
                <label htmlFor="birthday" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  生日
                </label>
                <input
                  id="birthday"
                  type="date"
                  value={profile.birthday}
                  onChange={(e) => setProfile({ ...profile, birthday: e.target.value })}
                  className={cn(
                    'w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all duration-200 bg-input border-2 border-border focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-background',
                    profile.birthday ? 'text-foreground' : 'text-muted-foreground'
                  )}
                />
              </div>

              {/* Gender */}
              <fieldset className="animate-fade-in-up" style={{ animationDelay: '100ms' }}>
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
                        'flex-1 py-3.5 rounded-xl text-sm font-medium transition-all duration-200 border-2 focus-ring relative overflow-hidden',
                        profile.gender === option.value 
                          ? 'bg-rose-soft border-rose text-primary scale-[1.02]'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80 active:scale-[0.98]'
                      )}
                      aria-pressed={profile.gender === option.value}
                    >
                      {profile.gender === option.value && (
                        <span className="absolute right-2 top-1/2 -translate-y-1/2">
                          <Check className="w-4 h-4 text-primary" />
                        </span>
                      )}
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Location */}
              <div className="animate-fade-in-up" style={{ animationDelay: '150ms' }}>
                <label htmlFor="location" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  所在城市
                </label>
                <input
                  id="location"
                  type="text"
                  value={profile.location}
                  onChange={(e) => setProfile({ ...profile, location: e.target.value })}
                  placeholder="你现在住在哪里"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all duration-200 bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-background"
                  autoComplete="address-level2"
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
                    'w-full p-5 rounded-2xl text-left transition-all duration-200 border-2 focus-ring animate-fade-in-up relative overflow-hidden',
                    profile.relationshipGoal === option.value 
                      ? 'bg-gradient-to-br from-rose-soft to-gold-soft/50 border-rose shadow-md scale-[1.01]'
                      : 'bg-card border-border hover:border-border/80 hover:bg-secondary/30 active:scale-[0.99]'
                  )}
                  style={{ animationDelay: `${index * 80}ms` }}
                  aria-pressed={profile.relationshipGoal === option.value}
                >
                  {profile.relationshipGoal === option.value && (
                    <span className="absolute right-4 top-4">
                      <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                        <Check className="w-4 h-4 text-primary-foreground" />
                      </div>
                    </span>
                  )}
                  <div className={cn(
                    'font-medium mb-1 transition-colors duration-200',
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
              <p className="text-sm mb-5 text-muted-foreground animate-fade-in-up">
                选择 3-8 个最能代表你的标签
                <span className={cn(
                  'ml-2 font-medium transition-colors duration-200',
                  profile.tags.length >= 3 ? 'text-primary' : 'text-rose'
                )}>
                  ({profile.tags.length}/8)
                </span>
              </p>
              
              <div className="flex flex-wrap gap-2.5" role="group" aria-label="个人标签选择">
                {AVAILABLE_TAGS.map((tag, index) => {
                  const isSelected = profile.tags.includes(tag)
                  return (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => toggleTag(tag)}
                      className={cn(
                        'px-4 py-2.5 rounded-full text-sm font-medium transition-all duration-200 border animate-scale-in focus-ring',
                        isSelected 
                          ? 'bg-primary text-primary-foreground border-transparent shadow-lg shadow-primary/25 scale-105'
                          : 'bg-card border-border text-secondary-foreground hover:border-primary/30 hover:bg-secondary/50 active:scale-95'
                      )}
                      style={{ animationDelay: `${index * 25}ms` }}
                      aria-pressed={isSelected}
                    >
                      {isSelected && <Check className="w-3.5 h-3.5 inline-block mr-1 -ml-1" />}
                      {tag}
                    </button>
                  )
                })}
              </div>
              
              {/* Selected tags summary */}
              {profile.tags.length > 0 && (
                <div className="mt-6 pt-4 border-t border-border animate-fade-in-up">
                  <p className="text-xs text-muted-foreground mb-2">已选择的标签：</p>
                  <div className="flex flex-wrap gap-1.5">
                    {profile.tags.map((tag) => (
                      <span 
                        key={tag}
                        className="px-2.5 py-1 bg-rose-soft text-primary text-xs rounded-full"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {currentStep === 'preferences' && (
            <div className="space-y-8">
              {/* Age range with custom slider */}
              <div className="animate-fade-in-up">
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
              <fieldset className="animate-fade-in-up" style={{ animationDelay: '100ms' }}>
                <legend className="block text-sm font-medium mb-3 text-secondary-foreground">
                  期望 TA 的位置
                </legend>
                <div className="space-y-2">
                  {[
                    { value: 'same_city', label: '同城', desc: '优先匹配同城' },
                    { value: 'nearby', label: '附近城市也可以', desc: '扩大搜索范围' },
                    { value: 'any', label: '不限制', desc: '全国范围匹配' },
                  ].map((option, index) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, locationPref: option.value })}
                      className={cn(
                        'w-full py-3.5 px-4 rounded-xl text-sm font-medium text-left transition-all duration-200 border-2 focus-ring flex items-center justify-between',
                        profile.locationPref === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80 hover:bg-secondary/30 active:scale-[0.99]'
                      )}
                      style={{ animationDelay: `${150 + index * 50}ms` }}
                      aria-pressed={profile.locationPref === option.value}
                    >
                      <div>
                        <div className={cn(
                          'transition-colors duration-200',
                          profile.locationPref === option.value ? 'text-primary' : 'text-foreground'
                        )}>
                          {option.label}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {option.desc}
                        </div>
                      </div>
                      {profile.locationPref === option.value && (
                        <Check className="w-5 h-5 text-primary flex-shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          )}
        </div>

        {/* CTA Button */}
        <div className="py-6 safe-area-bottom">
          <Button
            onClick={() => void handleNext()}
            disabled={!canProceed() || isSubmitting || isTransitioning}
            className={cn(
              'w-full h-12 rounded-2xl text-base gap-2 transition-all duration-300',
              canProceed() && !isSubmitting ? 'shadow-lg shadow-primary/25' : ''
            )}
            size="lg"
          >
            {isSubmitting ? (
              <>
                <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                保存中…
              </>
            ) : currentIndex === steps.length - 1 ? (
              <>
                <Check className="w-5 h-5" />
                完成
              </>
            ) : (
              <>
                下一步
                <ChevronRight className="w-5 h-5" aria-hidden="true" />
              </>
            )}
          </Button>
          
          {/* Step indicator dots */}
          <div className="flex justify-center gap-2 mt-4">
            {steps.map((step, index) => (
              <div
                key={step}
                className={cn(
                  'w-2 h-2 rounded-full transition-all duration-300',
                  index === currentIndex 
                    ? 'bg-primary w-6' 
                    : index < currentIndex 
                      ? 'bg-primary/60' 
                      : 'bg-border'
                )}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
