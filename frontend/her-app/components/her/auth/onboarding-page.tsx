'use client'

import { useState, useRef } from 'react'
import { ChevronLeft, Plus, X, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { applyLoginPayload } from '@/lib/auth/session'
import { notifyError, notifySuccess } from '@/lib/notify'
import { Button } from '@/components/ui/button'

interface OnboardingPageProps {
  onComplete: () => void
  onBack: () => void
}

type Step = 'intro' | 'reality' | 'goals'

interface ProfileData {
  name: string
  gender: string
  sexualOrientation: string
  birthday: string
  currentCity: string
  futureCity: string
  photos: string[]
  relationshipGoal: string
  marriageStatus: string
  hasChildren: string
}

export default function OnboardingPage({ 
  onComplete,
  onBack 
}: OnboardingPageProps) {
  const [currentStep, setCurrentStep] = useState<Step>('intro')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [slideDirection, setSlideDirection] = useState<'left' | 'right'>('left')
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const [profile, setProfile] = useState<ProfileData>({
    name: '',
    gender: '',
    sexualOrientation: '',
    birthday: '',
    currentCity: '',
    futureCity: '',
    photos: [],
    relationshipGoal: '',
    marriageStatus: '',
    hasChildren: '',
  })

  const steps: Step[] = ['intro', 'reality', 'goals']
  const currentIndex = steps.indexOf(currentStep)
  const progress = ((currentIndex + 1) / steps.length) * 100

  const handleNext = async () => {
    const nextIndex = currentIndex + 1
    if (nextIndex < steps.length) {
      setSlideDirection('left')
      setCurrentStep(steps[nextIndex])
      return
    }
    // Submit on final step
    setIsSubmitting(true)
    try {
      const result = await submitOnboarding({
        basic_info: {
          name: profile.name,
          birthday: profile.birthday,
          gender: profile.gender,
          sexual_orientation: profile.sexualOrientation,
          location: profile.currentCity,
          future_city: profile.futureCity,
          relationship_goal: profile.relationshipGoal,
          marriage_status: profile.marriageStatus,
          has_children: profile.hasChildren,
        },
        preference: {
          relationship_goal: profile.relationshipGoal,
        },
        photos: profile.photos,
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
      notifySuccess('资料已保存')
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
      setSlideDirection('right')
      setCurrentStep(steps[currentIndex - 1])
    }
  }

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files) {
      const newPhotos = Array.from(files).map(file => URL.createObjectURL(file))
      setProfile(prev => ({
        ...prev,
        photos: [...prev.photos, ...newPhotos].slice(0, 6)
      }))
    }
  }

  const removePhoto = (index: number) => {
    setProfile(prev => ({
      ...prev,
      photos: prev.photos.filter((_, i) => i !== index)
    }))
  }

  const canProceed = () => {
    switch (currentStep) {
      case 'intro':
        return profile.photos.length >= 1 && profile.name && profile.gender && profile.sexualOrientation
      case 'reality':
        return profile.birthday && profile.currentCity && profile.futureCity && profile.marriageStatus && profile.hasChildren
      case 'goals':
        return profile.relationshipGoal
      default:
        return false
    }
  }

  const stepConfig = {
    intro: { title: '先认识一下你', subtitle: '先把最基础的资料给我' },
    reality: { title: '再了解一点现实情况', subtitle: '这些会直接影响后面的匹配' },
    goals: { title: '你更期待哪种关系', subtitle: '我会按这个方向安排聊天和推荐' },
  }

  const config = stepConfig[currentStep]

  const getButtonText = () => {
    if (isSubmitting) return '保存中…'
    if (currentStep === 'goals') {
      return profile.relationshipGoal ? '完成' : '请选择一个方向'
    }
    return '下一步'
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/20 via-background to-background" />
        <div className="grain-texture absolute inset-0" />
      </div>

      {/* Header - minimal, light progress feel */}
      <header className="relative z-10 px-6 pt-14 pb-2">
        <div className="flex items-center mb-4">
          <button 
            onClick={handlePrev}
            className="w-10 h-10 rounded-full flex items-center justify-center transition-colors hover:bg-secondary/80 focus-ring"
            aria-label={currentIndex === 0 ? '返回' : '上一步'}
          >
            <ChevronLeft className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Progress bar - very light, no numbers */}
        <div 
          className="h-1 rounded-full overflow-hidden bg-secondary/50"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div 
            className="h-full rounded-full bg-primary/60 transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </header>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col px-6 pt-6 overflow-y-auto">
        
        {/* Step header - simple, no icons */}
        <div 
          key={currentStep}
          className={cn(
            'mb-8',
            slideDirection === 'left' ? 'animate-slide-in-right' : 'animate-slide-in-left'
          )}
        >
          <h1 className="text-2xl font-semibold mb-2 text-foreground">
            {config.title}
          </h1>
          <p className="text-sm text-muted-foreground">
            {config.subtitle}
          </p>
        </div>

        {/* Step content with slide animation */}
        <div 
          key={`content-${currentStep}`}
          className={cn(
            'flex-1',
            slideDirection === 'left' ? 'animate-slide-in-right' : 'animate-slide-in-left'
          )}
        >
          {/* Step 1: 先认识你 - Photo first, then basic info */}
          {currentStep === 'intro' && (
            <div className="space-y-6">
              {/* Photo Upload Card - prominent, first thing user sees */}
              <div className="rounded-2xl border-2 border-dashed border-border p-6 bg-card/50">
                <div className="text-center mb-4">
                  <h3 className="font-medium text-foreground mb-1">上传一张本人照片</h3>
                  <p className="text-sm text-muted-foreground">先传 1 张就可以，后面再补也行</p>
                </div>
                
                <div className="flex flex-wrap gap-3 justify-center">
                  {profile.photos.map((photo, index) => (
                    <div 
                      key={index} 
                      className="relative w-20 h-20 rounded-xl overflow-hidden bg-secondary animate-scale-in"
                    >
                      <img 
                        src={photo} 
                        alt={`照片 ${index + 1}`}
                        className="w-full h-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => removePhoto(index)}
                        className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 flex items-center justify-center text-white hover:bg-black/80 transition-colors"
                        aria-label={`删除照片 ${index + 1}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                  
                  {profile.photos.length < 6 && (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className={cn(
                        'w-20 h-20 rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-1 transition-all',
                        profile.photos.length === 0 
                          ? 'border-primary bg-primary/5 text-primary' 
                          : 'border-border text-muted-foreground hover:border-primary hover:text-primary'
                      )}
                    >
                      <Plus className="w-5 h-5" />
                      <span className="text-xs">{profile.photos.length === 0 ? '选择' : '添加'}</span>
                    </button>
                  )}
                </div>
                
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={handlePhotoUpload}
                  className="hidden"
                />
              </div>

              {/* Name */}
              <div>
                <label htmlFor="name" className="block text-sm font-medium mb-2 text-foreground">
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

              {/* Gender - 3 options */}
              <fieldset>
                <legend className="block text-sm font-medium mb-3 text-foreground">
                  性别
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'female', label: '女' },
                    { value: 'male', label: '男' },
                    { value: 'other', label: '其他' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, gender: option.value })}
                      className={cn(
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all duration-200 border-2 focus-ring',
                        profile.gender === option.value 
                          ? 'bg-primary text-primary-foreground border-primary scale-[1.02]'
                          : 'bg-input border-border text-muted-foreground hover:border-primary/30 active:scale-[0.98]'
                      )}
                      aria-pressed={profile.gender === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Sexual Orientation - conversational labels */}
              <fieldset>
                <legend className="block text-sm font-medium mb-3 text-foreground">
                  你喜欢
                </legend>
                <div className="flex flex-wrap gap-2">
                  {[
                    { value: 'like_male', label: '喜欢男生' },
                    { value: 'like_female', label: '喜欢女生' },
                    { value: 'both', label: '都可以' },
                    { value: 'undecided', label: '还不想细分' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, sexualOrientation: option.value })}
                      className={cn(
                        'px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 border-2 focus-ring',
                        profile.sexualOrientation === option.value 
                          ? 'bg-primary text-primary-foreground border-primary scale-[1.02]'
                          : 'bg-input border-border text-muted-foreground hover:border-primary/30 active:scale-[0.98]'
                      )}
                      aria-pressed={profile.sexualOrientation === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          )}

          {/* Step 2: 现实情况 - stacked short modules */}
          {currentStep === 'reality' && (
            <div className="space-y-5">
              {/* Birthday - no extra explanation */}
              <div>
                <label htmlFor="birthday" className="block text-sm font-medium mb-2 text-foreground">
                  出生年月日
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

              {/* Current City */}
              <div>
                <label htmlFor="currentCity" className="block text-sm font-medium mb-2 text-foreground">
                  你现在长期在哪座城市
                </label>
                <input
                  id="currentCity"
                  type="text"
                  value={profile.currentCity}
                  onChange={(e) => setProfile({ ...profile, currentCity: e.target.value })}
                  placeholder="例如 上海"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Future City */}
              <div>
                <label htmlFor="futureCity" className="block text-sm font-medium mb-2 text-foreground">
                  你更想定居在哪里
                </label>
                <input
                  id="futureCity"
                  type="text"
                  value={profile.futureCity}
                  onChange={(e) => setProfile({ ...profile, futureCity: e.target.value })}
                  placeholder="例如 杭州"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Marriage Status */}
              <fieldset>
                <legend className="block text-sm font-medium mb-3 text-foreground">
                  目前婚况
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'never_married', label: '未婚' },
                    { value: 'divorced', label: '离异' },
                    { value: 'widowed', label: '丧偶' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, marriageStatus: option.value })}
                      className={cn(
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all duration-200 border-2 focus-ring',
                        profile.marriageStatus === option.value 
                          ? 'bg-primary text-primary-foreground border-primary scale-[1.02]'
                          : 'bg-input border-border text-muted-foreground hover:border-primary/30 active:scale-[0.98]'
                      )}
                      aria-pressed={profile.marriageStatus === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Has Children */}
              <fieldset>
                <legend className="block text-sm font-medium mb-3 text-foreground">
                  是否有孩子
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'no', label: '没有' },
                    { value: 'yes', label: '有' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, hasChildren: option.value })}
                      className={cn(
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all duration-200 border-2 focus-ring',
                        profile.hasChildren === option.value 
                          ? 'bg-primary text-primary-foreground border-primary scale-[1.02]'
                          : 'bg-input border-border text-muted-foreground hover:border-primary/30 active:scale-[0.98]'
                      )}
                      aria-pressed={profile.hasChildren === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          )}

          {/* Step 3: 关系目标 - 3 large cards only */}
          {currentStep === 'goals' && (
            <div className="space-y-4">
              {[
                { 
                  value: 'marriage', 
                  title: '奔着结婚去', 
                  desc: '目标明确，希望认真推进' 
                },
                { 
                  value: 'dating', 
                  title: '先谈恋爱看', 
                  desc: '先看相处和感觉，再决定往哪里走' 
                },
                { 
                  value: 'friends', 
                  title: '找搭子 / 扩列', 
                  desc: '先认识合拍的人，轻松一点开始' 
                },
              ].map((option) => {
                const isSelected = profile.relationshipGoal === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setProfile({ ...profile, relationshipGoal: option.value })}
                    className={cn(
                      'w-full p-5 rounded-2xl text-left transition-all duration-200 border-2 focus-ring relative',
                      isSelected 
                        ? 'bg-primary/5 border-primary shadow-sm scale-[1.01]'
                        : 'bg-card border-border hover:border-primary/30 active:scale-[0.99]'
                    )}
                    aria-pressed={isSelected}
                  >
                    {isSelected && (
                      <span className="absolute right-4 top-1/2 -translate-y-1/2">
                        <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                          <Check className="w-4 h-4 text-primary-foreground" />
                        </div>
                      </span>
                    )}
                    <div className={cn(
                      'font-semibold text-base mb-1 pr-8 transition-colors duration-200',
                      isSelected ? 'text-primary' : 'text-foreground'
                    )}>
                      {option.title}
                    </div>
                    <div className="text-sm text-muted-foreground pr-8">
                      {option.desc}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* CTA Button - always one button at bottom */}
        <div className="py-6 safe-area-bottom">
          <Button
            onClick={() => void handleNext()}
            disabled={!canProceed() || isSubmitting}
            className={cn(
              'w-full h-12 rounded-2xl text-base transition-all duration-200',
              canProceed() && !isSubmitting ? 'shadow-lg shadow-primary/20' : ''
            )}
            size="lg"
          >
            {getButtonText()}
          </Button>
        </div>
      </div>
    </div>
  )
}
