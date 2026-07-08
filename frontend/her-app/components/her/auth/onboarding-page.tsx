'use client'

import { useState, useRef, useEffect, useCallback, useId } from 'react'
import { ChevronLeft, X, Check, ImagePlus, Heart, Users, Sparkles, Loader2, Crown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { applyLoginPayload } from '@/lib/auth/session'
import { clearStoredDiscoverySessionId } from '@/lib/discovery/session-storage'
import { notifyError, notifySuccess } from '@/lib/notify'
import { Button } from '@/components/ui/button'
import { CitySelector } from '@/components/her/ui/city-selector'
import { DateWheelPicker } from '@/components/her/ui/date-wheel-picker'
import { uploadImage, compressImage } from '@/lib/api/endpoints/media'

const STORAGE_KEY = 'her_onboarding_draft'

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
  photos: string[]
  avatarIndex: number  // 新增：头像索引（默认为0，即第一张照片）
  relationshipGoal: string
  marriageStatus: string
  hasChildren: string
}

const EMPTY_PROFILE: ProfileData = {
  name: '',
  gender: '',
  sexualOrientation: '',
  birthday: '',
  currentCity: '',
  photos: [],
  avatarIndex: 0,  // 新增：默认第一张照片为头像
  relationshipGoal: '',
  marriageStatus: '',
  hasChildren: '',
}

export default function OnboardingPage({ 
  onComplete,
  onBack 
}: OnboardingPageProps) {
  const [currentStep, setCurrentStep] = useState<Step>('intro')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [slideDirection, setSlideDirection] = useState<'left' | 'right'>('left')
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const photoInputId = useId()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  
  // Same initial state on server and client; load draft after mount to avoid hydration mismatch
  const [profile, setProfile] = useState<ProfileData>(EMPTY_PROFILE)
  const [draftLoaded, setDraftLoaded] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        setProfile(JSON.parse(saved) as ProfileData)
      } catch {
        // ignore parse errors
      }
    }
    setDraftLoaded(true)
  }, [])

  useEffect(() => {
    if (!draftLoaded) return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
    } catch {
      // Ignore quota errors from large photo drafts.
    }
  }, [profile, draftLoaded])

  // Clear draft on successful completion
  const clearDraft = useCallback(() => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  const steps: Step[] = ['intro', 'reality', 'goals']
  const currentIndex = steps.indexOf(currentStep)
  const progress = ((currentIndex + 1) / steps.length) * 100

  // Scroll to top when step changes
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [currentStep])

  // Get missing fields for current step
  const getMissingFields = (): string[] => {
    switch (currentStep) {
      case 'intro': {
        const introMissing: string[] = []
        if (profile.photos.length < 1) introMissing.push('照片')
        if (!profile.name) introMissing.push('名字')
        if (!profile.gender) introMissing.push('性别')
        if (!profile.sexualOrientation) introMissing.push('喜欢的类型')
        return introMissing
      }
      case 'reality': {
        const realityMissing: string[] = []
        if (!profile.birthday) realityMissing.push('生日')
        if (!profile.currentCity) realityMissing.push('城市')
        if (!profile.marriageStatus) realityMissing.push('婚况')
        if (!profile.hasChildren) realityMissing.push('是否有孩子')
        return realityMissing
      }
      case 'goals':
        if (!profile.relationshipGoal) return ['关系目标']
        return []
      default:
        return []
    }
  }

  const handleNext = async () => {
    const missing = getMissingFields()
    if (missing.length > 0) {
      setValidationErrors(missing)
      // Auto-clear after 3 seconds
      setTimeout(() => setValidationErrors([]), 3000)
      return
    }

    setValidationErrors([])
    const nextIndex = currentIndex + 1
    if (nextIndex < steps.length) {
      setSlideDirection('left')
      setCurrentStep(steps[nextIndex])
      return
    }
    // Submit on final step
    setIsSubmitting(true)
    try {
      // 新增：调整照片顺序，把头像照片放在第一位
      const reorderedPhotos = profile.avatarIndex === 0
        ? profile.photos  // 如果头像已经是第一张，不需要调整
        : [
            profile.photos[profile.avatarIndex],  // 头像照片移到第一位
            ...profile.photos.slice(0, profile.avatarIndex),  // 原头像之前的照片
            ...profile.photos.slice(profile.avatarIndex + 1)  // 原头像之后的照片
          ]

      console.log('[handleNext] 提交到后端', {
        currentStep: currentStep,
        photosCount: profile.photos.length,
        avatarIndex: profile.avatarIndex,
        reorderedPhotos: reorderedPhotos,
        photosType: typeof reorderedPhotos,
        photosArrayType: reorderedPhotos.map(p => typeof p),
      })

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
        preference: {
          relationship_goal: profile.relationshipGoal,
        },
        photos: reorderedPhotos,  // 使用重新排序后的照片列表
        mark_completed: true,
      })
      console.log('[handleNext] 提交成功，返回结果', result)
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
      if (typeof result.profile_id === 'number' && result.profile_id > 0) {
        clearStoredDiscoverySessionId(result.profile_id)
      }
      clearDraft()
      notifySuccess('资料已保存')
      onComplete()
    } catch (error) {
      console.error('[handleNext] 提交失败', error)
      notifyError(error, '资料保存失败，请重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handlePrev = () => {
    setValidationErrors([])
    if (currentIndex === 0) {
      onBack()
    } else {
      setSlideDirection('right')
      setCurrentStep(steps[currentIndex - 1])
    }
  }

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    console.log('[handlePhotoUpload] 开始处理照片上传', {
      filesCount: files.length,
      currentPhotos: profile.photos,
    })

    setIsUploading(true)
    try {
      const newPhotos: string[] = []
      for (const file of Array.from(files)) {
        console.log('[handlePhotoUpload] 处理文件', {
          fileName: file.name,
          fileSize: file.size,
          fileType: file.type,
        })

        // Step 1: 前端压缩（使用API的compressImage函数）
        const compressedFile = await compressImage(file)
        console.log('[handlePhotoUpload] 压缩完成', {
          compressedSize: compressedFile.size,
        })

        // Step 2: 上传到MinIO（使用API的uploadImage函数）
        const result = await uploadImage(compressedFile)
        console.log('[handlePhotoUpload] 上传完成，mediaUrl', result.mediaUrl)

        // Step 3: 保存media_url（而非base64 DataURL）
        newPhotos.push(result.mediaUrl)
      }

      console.log('[handlePhotoUpload] 所有照片处理完成', {
        newPhotosCount: newPhotos.length,
        newPhotos: newPhotos,
      })

      setProfile(prev => ({
        ...prev,
        photos: [...prev.photos, ...newPhotos].slice(0, 6)
      }))
      notifySuccess('照片上传成功')
    } catch (error) {
      console.error('[handlePhotoUpload] 照片上传失败', error)
      notifyError(error, '照片上传失败')
    } finally {
      setIsUploading(false)
      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const removePhoto = (index: number) => {
    setProfile(prev => {
      const newPhotos = prev.photos.filter((_, i) => i !== index)
      // 新增：调整avatarIndex
      let newAvatarIndex = prev.avatarIndex
      if (index === prev.avatarIndex) {
        // 如果删除的是头像照片，默认设置下一张（或第一张）为头像
        newAvatarIndex = Math.min(prev.avatarIndex, newPhotos.length - 1)
      } else if (index < prev.avatarIndex) {
        // 如果删除的照片在头像之前，avatarIndex需要减1
        newAvatarIndex = prev.avatarIndex - 1
      }
      return {
        ...prev,
        photos: newPhotos,
        avatarIndex: newAvatarIndex
      }
    })
  }

  // 新增：设置头像
  const setAvatar = (index: number) => {
    setProfile(prev => ({
      ...prev,
      avatarIndex: index
    }))
  }

  const canProceed = () => {
    switch (currentStep) {
      case 'intro':
        return profile.photos.length >= 1 && profile.name && profile.gender && profile.sexualOrientation
      case 'reality':
        return profile.birthday && profile.currentCity && profile.marriageStatus && profile.hasChildren
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

  // Goal icons and colors
  const goalConfig = {
    marriage: { icon: Heart, color: 'text-rose', bgColor: 'bg-rose-soft' },
    dating: { icon: Sparkles, color: 'text-gold', bgColor: 'bg-gold-soft' },
    friends: { icon: Users, color: 'text-primary', bgColor: 'bg-primary/10' },
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/20 via-background to-background pointer-events-none" />
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
      <div 
        ref={contentRef}
        className="relative z-10 flex-1 flex flex-col px-6 pt-6 overflow-y-auto scrollbar-hide"
      >
        
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

        {/* Validation errors */}
        {validationErrors.length > 0 && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-destructive/10 border border-destructive/20 animate-fade-in-up">
            <p className="text-sm text-destructive">
              请填写：{validationErrors.join('、')}
            </p>
          </div>
        )}

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
                <input
                  id={photoInputId}
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/*"
                  multiple
                  onChange={handlePhotoUpload}
                  className="sr-only"
                  disabled={isUploading || profile.photos.length >= 6}
                />

                <label
                  htmlFor={photoInputId}
                  className={cn(
                    'block text-center mb-4 transition-opacity',
                    isUploading || profile.photos.length >= 6
                      ? 'cursor-default opacity-60'
                      : 'cursor-pointer'
                  )}
                >
                  <h3 className="font-medium text-foreground mb-1">上传一张本人照片</h3>
                  <p className="text-sm text-muted-foreground">先传 1 张就可以，后面再补也行</p>
                </label>
                
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
                      {/* 新增：头像标识 */}
                      {index === profile.avatarIndex && (
                        <div className="absolute top-1 left-1 w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                          <Crown className="w-3 h-3 text-primary-foreground" />
                        </div>
                      )}
                      {/* 删除按钮 */}
                      <button
                        type="button"
                        onClick={() => removePhoto(index)}
                        className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 flex items-center justify-center text-white hover:bg-black/80 transition-colors"
                        aria-label={`删除照片 ${index + 1}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                      {/* 新增：设置头像按钮（仅在不是头像时显示） */}
                      {index !== profile.avatarIndex && (
                        <button
                          type="button"
                          onClick={() => setAvatar(index)}
                          className="absolute bottom-1 left-1/2 -translate-x-1/2 w-auto px-2 py-1 rounded-full bg-primary/80 flex items-center justify-center text-primary-foreground hover:bg-primary transition-colors text-xs"
                          aria-label={`将照片 ${index + 1} 设为头像`}
                        >
                          <Crown className="w-3 h-3 mr-1" />
                          设为头像
                        </button>
                      )}
                    </div>
                  ))}
                  
                  {profile.photos.length < 6 && (
                    <label
                      htmlFor={photoInputId}
                      aria-label={profile.photos.length === 0 ? '选择照片' : '添加照片'}
                      className={cn(
                        'w-20 h-20 rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-1 transition-all',
                        isUploading
                          ? 'border-muted cursor-not-allowed opacity-60'
                          : profile.photos.length === 0
                            ? 'border-primary bg-primary/5 text-primary cursor-pointer'
                            : 'border-border text-muted-foreground hover:border-primary hover:text-primary cursor-pointer'
                      )}
                    >
                      {isUploading ? (
                        <Loader2 className="w-5 h-5 animate-spin" />
                      ) : (
                        <>
                          <ImagePlus className="w-5 h-5" />
                          <span className="text-xs">{profile.photos.length === 0 ? '选择' : '添加'}</span>
                        </>
                      )}
                    </label>
                  )}
                </div>
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
                  autoComplete="off"
                />
              </div>

              {/* Gender - 2 options */}
              <fieldset>
                <legend className="block text-sm font-medium mb-3 text-foreground">
                  性别
                </legend>
                <div className="flex gap-3">
                  {[
                    { value: 'female', label: '女' },
                    { value: 'male', label: '男' },
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
              {/* Birthday - wheel picker */}
              <div>
                <label className="block text-sm font-medium mb-2 text-foreground">
                  出生年月日
                </label>
                <DateWheelPicker
                  value={profile.birthday}
                  onChange={(date) => setProfile({ ...profile, birthday: date })}
                  placeholder="选择你的生日"
                />
              </div>

              {/* Current City - selector */}
              <div>
                <label className="block text-sm font-medium mb-2 text-foreground">
                  你现在长期在哪座城市
                </label>
                <CitySelector
                  value={profile.currentCity}
                  onChange={(city) => setProfile({ ...profile, currentCity: city })}
                  placeholder="选择城市"
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

          {/* Step 3: 关系目标 - 3 large cards with icons */}
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
                const config = goalConfig[option.value as keyof typeof goalConfig]
                const IconComponent = config.icon
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
                    <div className="flex items-start gap-4">
                      {/* Icon */}
                      <div className={cn(
                        'w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 transition-all',
                        isSelected ? config.bgColor : 'bg-secondary'
                      )}>
                        <IconComponent className={cn(
                          'w-6 h-6 transition-colors',
                          isSelected ? config.color : 'text-muted-foreground'
                        )} />
                      </div>
                      
                      <div className="flex-1 pr-8">
                        <div className={cn(
                          'font-semibold text-base mb-1 transition-colors duration-200',
                          isSelected ? 'text-primary' : 'text-foreground'
                        )}>
                          {option.title}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {option.desc}
                        </div>
                      </div>
                    </div>
                    
                    {isSelected && (
                      <span className="absolute right-4 top-1/2 -translate-y-1/2">
                        <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                          <Check className="w-4 h-4 text-primary-foreground" />
                        </div>
                      </span>
                    )}
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
