'use client'

import { useState, useRef } from 'react'
import { ChevronLeft, ChevronRight, User, Heart, Camera, Sparkles, Plus, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { applyLoginPayload } from '@/lib/auth/session'
import { notifyError, notifySuccess } from '@/lib/notify'
import { Button } from '@/components/ui/button'

interface OnboardingPageProps {
  onComplete: () => void
  onBack: () => void
}

type Step = 'basics' | 'details' | 'photos' | 'optional'

interface ProfileData {
  // Required
  name: string
  gender: string
  sexualOrientation: string
  birthday: string
  currentCity: string
  photos: string[]
  relationshipGoal: string
  marriageStatus: string
  hasChildren: string
  // Optional
  height: string
  occupation: string
  education: string
  acceptLongDistance: string
  meetingPace: string
  bio: string
}

export default function OnboardingPage({ 
  onComplete,
  onBack 
}: OnboardingPageProps) {
  const [currentStep, setCurrentStep] = useState<Step>('basics')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  
  const [profile, setProfile] = useState<ProfileData>({
    name: '',
    gender: '',
    sexualOrientation: '',
    birthday: '',
    currentCity: '',
    photos: [],
    relationshipGoal: '',
    marriageStatus: '',
    hasChildren: '',
    height: '',
    occupation: '',
    education: '',
    acceptLongDistance: '',
    meetingPace: '',
    bio: '',
  })

  const steps: Step[] = ['basics', 'details', 'photos', 'optional']
  const currentIndex = steps.indexOf(currentStep)
  const progress = ((currentIndex + 1) / steps.length) * 100

  const handleNext = async () => {
    const nextIndex = currentIndex + 1
    if (nextIndex < steps.length) {
      setCurrentStep(steps[nextIndex])
      return
    }
    setIsSubmitting(true)
    try {
      const result = await submitOnboarding({
        basic_info: {
          name: profile.name,
          birthday: profile.birthday,
          gender: profile.gender,
          sexual_orientation: profile.sexualOrientation,
          location: profile.currentCity,
          relationship_goal: profile.relationshipGoal,
          marriage_status: profile.marriageStatus,
          has_children: profile.hasChildren,
          height: profile.height,
          occupation: profile.occupation,
          education: profile.education,
          bio: profile.bio,
        },
        preference: {
          relationship_goal: profile.relationshipGoal,
          accept_long_distance: profile.acceptLongDistance,
          meeting_pace: profile.meetingPace,
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
      setCurrentStep(steps[currentIndex - 1])
    }
  }

  const handleSkipOptional = async () => {
    setIsSubmitting(true)
    try {
      const result = await submitOnboarding({
        basic_info: {
          name: profile.name,
          birthday: profile.birthday,
          gender: profile.gender,
          sexual_orientation: profile.sexualOrientation,
          location: profile.currentCity,
          relationship_goal: profile.relationshipGoal,
          marriage_status: profile.marriageStatus,
          has_children: profile.hasChildren,
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

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files) {
      // In real app, upload to server and get URLs
      // For now, create object URLs as placeholders
      const newPhotos = Array.from(files).map(file => URL.createObjectURL(file))
      setProfile(prev => ({
        ...prev,
        photos: [...prev.photos, ...newPhotos].slice(0, 6) // Max 6 photos
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
      case 'basics':
        return profile.name && profile.gender && profile.sexualOrientation && profile.birthday
      case 'details':
        return profile.currentCity && profile.relationshipGoal && profile.marriageStatus && profile.hasChildren
      case 'photos':
        return profile.photos.length >= 1
      case 'optional':
        return true
      default:
        return false
    }
  }

  const stepConfig = {
    basics: { icon: User, title: '基本信息', subtitle: '让我先认识你' },
    details: { icon: Heart, title: '更多信息', subtitle: '帮助我们更好地匹配' },
    photos: { icon: Camera, title: '上传照片', subtitle: '至少上传 1 张照片' },
    optional: { icon: Sparkles, title: '补充信息', subtitle: '选填，可以跳过' },
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
      <div className="relative z-10 flex-1 flex flex-col px-8 pt-4 overflow-y-auto">
        
        {/* Step header */}
        <div className="flex items-center gap-4 mb-6 animate-fade-in-up">
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
                  姓名 <span className="text-rose">*</span>
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

              {/* Gender */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  性别 <span className="text-rose">*</span>
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
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
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

              {/* Sexual Orientation */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  性取向 <span className="text-rose">*</span>
                </legend>
                <div className="flex flex-wrap gap-2">
                  {[
                    { value: 'straight', label: '异性恋' },
                    { value: 'gay', label: '同性恋' },
                    { value: 'bisexual', label: '双性恋' },
                    { value: 'other', label: '其他' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, sexualOrientation: option.value })}
                      className={cn(
                        'px-4 py-2.5 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.sexualOrientation === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.sexualOrientation === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Birthday */}
              <div>
                <label htmlFor="birthday" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  出生年月日 <span className="text-rose">*</span>
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
            </div>
          )}

          {currentStep === 'details' && (
            <div className="space-y-5">
              {/* Current City */}
              <div>
                <label htmlFor="currentCity" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  当前常驻城市 <span className="text-rose">*</span>
                </label>
                <input
                  id="currentCity"
                  type="text"
                  value={profile.currentCity}
                  onChange={(e) => setProfile({ ...profile, currentCity: e.target.value })}
                  placeholder="你现在住在哪里"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Relationship Goal */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  核心期望 <span className="text-rose">*</span>
                </legend>
                <div className="space-y-2">
                  {[
                    { value: 'marriage', label: '奔着结婚去' },
                    { value: 'dating', label: '先谈恋爱看' },
                    { value: 'friends', label: '找搭子 / 扩列' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, relationshipGoal: option.value })}
                      className={cn(
                        'w-full py-3.5 px-4 rounded-xl text-sm font-medium text-left transition-all border-2 focus-ring',
                        profile.relationshipGoal === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.relationshipGoal === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Marriage Status */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  婚况 <span className="text-rose">*</span>
                </legend>
                <div className="flex flex-wrap gap-2">
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
                        'px-4 py-2.5 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.marriageStatus === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
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
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  是否有孩子 <span className="text-rose">*</span>
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
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.hasChildren === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
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

          {currentStep === 'photos' && (
            <div>
              <p className="text-sm mb-4 text-muted-foreground">
                上传 1-6 张照片展示真实的你
              </p>
              
              <div className="grid grid-cols-3 gap-3">
                {profile.photos.map((photo, index) => (
                  <div key={index} className="relative aspect-square rounded-xl overflow-hidden bg-secondary">
                    <img 
                      src={photo} 
                      alt={`照片 ${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => removePhoto(index)}
                      className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/50 flex items-center justify-center text-white hover:bg-black/70 transition-colors"
                      aria-label={`删除照片 ${index + 1}`}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                
                {profile.photos.length < 6 && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="aspect-square rounded-xl border-2 border-dashed border-border flex flex-col items-center justify-center gap-2 text-muted-foreground hover:border-primary hover:text-primary transition-colors"
                  >
                    <Plus className="w-6 h-6" />
                    <span className="text-xs">添加照片</span>
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
              
              <p className="text-xs text-muted-foreground mt-4">
                建议上传清晰的正面照，展示你的真实样貌
              </p>
            </div>
          )}

          {currentStep === 'optional' && (
            <div className="space-y-5">
              {/* Height */}
              <div>
                <label htmlFor="height" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  身高
                </label>
                <input
                  id="height"
                  type="text"
                  value={profile.height}
                  onChange={(e) => setProfile({ ...profile, height: e.target.value })}
                  placeholder="例如：170cm"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Occupation */}
              <div>
                <label htmlFor="occupation" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  职业
                </label>
                <input
                  id="occupation"
                  type="text"
                  value={profile.occupation}
                  onChange={(e) => setProfile({ ...profile, occupation: e.target.value })}
                  placeholder="你的职业"
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Education */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  学历
                </legend>
                <div className="flex flex-wrap gap-2">
                  {[
                    { value: 'high_school', label: '高中' },
                    { value: 'college', label: '大专' },
                    { value: 'bachelor', label: '本科' },
                    { value: 'master', label: '硕士' },
                    { value: 'phd', label: '博士' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, education: option.value })}
                      className={cn(
                        'px-4 py-2.5 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.education === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.education === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Accept Long Distance */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  是否接受异地
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'yes', label: '接受' },
                    { value: 'no', label: '不接受' },
                    { value: 'depends', label: '看情况' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, acceptLongDistance: option.value })}
                      className={cn(
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.acceptLongDistance === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.acceptLongDistance === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Meeting Pace */}
              <fieldset>
                <legend className="block text-sm font-medium mb-2 text-secondary-foreground">
                  是否愿意见面节奏快一点
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'fast', label: '愿意' },
                    { value: 'slow', label: '慢慢来' },
                  ].map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setProfile({ ...profile, meetingPace: option.value })}
                      className={cn(
                        'flex-1 py-3 rounded-xl text-sm font-medium transition-all border-2 focus-ring',
                        profile.meetingPace === option.value 
                          ? 'bg-rose-soft border-rose text-primary'
                          : 'bg-input border-border text-muted-foreground hover:border-border/80'
                      )}
                      aria-pressed={profile.meetingPace === option.value}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              {/* Bio */}
              <div>
                <label htmlFor="bio" className="block text-sm font-medium mb-2 text-secondary-foreground">
                  个人一句话介绍
                </label>
                <textarea
                  id="bio"
                  value={profile.bio}
                  onChange={(e) => setProfile({ ...profile, bio: e.target.value })}
                  placeholder="用一句话介绍自己"
                  rows={2}
                  maxLength={50}
                  className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary resize-none"
                />
                <p className="text-xs text-muted-foreground mt-1 text-right">
                  {profile.bio.length}/50
                </p>
              </div>
            </div>
          )}
        </div>

        {/* CTA Buttons */}
        <div className="py-6 safe-area-bottom space-y-3">
          {currentStep === 'optional' && (
            <Button
              variant="outline"
              onClick={() => void handleSkipOptional()}
              disabled={isSubmitting}
              className="w-full h-12 rounded-2xl text-base"
              size="lg"
            >
              跳过，稍后再填
            </Button>
          )}
          <Button
            onClick={() => void handleNext()}
            disabled={!canProceed() || isSubmitting}
            className="w-full h-12 rounded-2xl text-base gap-2"
            size="lg"
          >
            {isSubmitting ? '保存中…' : currentIndex === steps.length - 1 ? '完成' : '下一步'}
            {currentIndex < steps.length - 1 && <ChevronRight className="w-5 h-5" aria-hidden="true" />}
          </Button>
        </div>
      </div>
    </div>
  )
}
