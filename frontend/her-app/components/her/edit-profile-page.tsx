'use client'

import { useState, useRef, useEffect, useCallback, useId } from 'react'
import { X, Check, ImagePlus, Heart, Users, Sparkles, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { applyLoginPayload } from '@/lib/auth/session'
import { notifyError, notifySuccess } from '@/lib/notify'
import { Button } from '@/components/ui/button'
import { CitySelector } from '@/components/her/ui/city-selector'
import { DateWheelPicker } from '@/components/her/ui/date-wheel-picker'
import { useProfilePageData } from '@/lib/hooks/use-profile-page-data'
import { PageHeader } from '@/components/her/ui/page-header'
import { SlideInTransition } from '@/components/her/ui/page-transitions'

interface EditProfilePageProps {
  onBack: () => void
  onSaved: () => void
}

interface ProfileData {
  name: string
  gender: string
  sexualOrientation: string
  birthday: string
  currentCity: string
  photos: string[]
  relationshipGoal: string
  marriageStatus: string
  hasChildren: string
}

// Compress image before upload
async function compressImage(file: File, maxWidth = 1200, quality = 0.8): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        const canvas = document.createElement('canvas')
        let width = img.width
        let height = img.height

        if (width > maxWidth) {
          height = (height * maxWidth) / width
          width = maxWidth
        }

        canvas.width = width
        canvas.height = height

        const ctx = canvas.getContext('2d')
        if (!ctx) {
          reject(new Error('Failed to get canvas context'))
          return
        }

        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.onerror = reject
      img.src = e.target?.result as string
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function EditProfilePage({ onBack, onSaved }: EditProfilePageProps) {
  const { auth, facts, isLoading, refetch } = useProfilePageData()

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const photoInputId = useId()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  // 从已有数据初始化表单状态
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
  })

  // 数据加载完成后初始化表单
  useEffect(() => {
    if (!isLoading && (auth || facts)) {
      const rawProfile = facts?.profile_facts ?? {}
      const user = auth?.user ?? {}

      setProfile({
        name: (rawProfile.name as string) || (user.display_name as string) || '',
        gender: (rawProfile.gender as string) || '',
        sexualOrientation: (rawProfile.sexual_orientation as string) || '',
        birthday: (rawProfile.birthday as string) || '',
        currentCity: (rawProfile.city as string) || (rawProfile.settlement_city as string) || '',
        photos: (rawProfile.photos as string[]) || (rawProfile.avatar_url ? [rawProfile.avatar_url as string] : []),
        relationshipGoal: (rawProfile.relationship_goal as string) || '',
        marriageStatus: (rawProfile.marital_status as string) || (rawProfile.marriage_status as string) || '',
        hasChildren: (rawProfile.has_children as string) || (rawProfile.parenting_status as string) || '',
      })
    }
  }, [isLoading, auth, facts])

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    setIsUploading(true)
    try {
      const newPhotos: string[] = []
      for (const file of Array.from(files)) {
        const compressed = await compressImage(file)
        newPhotos.push(compressed)
      }
      setProfile(prev => ({
        ...prev,
        photos: [...prev.photos, ...newPhotos].slice(0, 6)
      }))
    } catch (error) {
      notifyError(error, '图片处理失败')
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const removePhoto = (index: number) => {
    setProfile(prev => ({
      ...prev,
      photos: prev.photos.filter((_, i) => i !== index)
    }))
  }

  const handleSave = async () => {
    // 轻量验证
    const errors: string[] = []
    if (profile.name && profile.name.length > 50) {
      errors.push('名字最长50字符')
    }
    if (profile.birthday) {
      const birthDate = new Date(profile.birthday)
      const today = new Date()
      const age = Math.floor((today.getTime() - birthDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000))
      if (age < 18) {
        errors.push('年龄需满18岁')
      }
    }

    if (errors.length > 0) {
      setValidationErrors(errors)
      setTimeout(() => setValidationErrors([]), 3000)
      return
    }

    setValidationErrors([])
    setIsSubmitting(true)

    try {
      const result = await submitOnboarding({
        basic_info: {
          name: profile.name,
          birthday: profile.birthday,
          gender: profile.gender,
          sexual_orientation: profile.sexualOrientation,
          location: profile.currentCity,
          city: profile.currentCity,
          relationship_goal: profile.relationshipGoal,
          marriage_status: profile.marriageStatus,
          has_children: profile.hasChildren,
        },
        preference: {
          relationship_goal: profile.relationshipGoal,
        },
        photos: profile.photos,
        mark_completed: false, // 编辑模式不标记完成
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

      await refetch()
      notifySuccess('资料已更新')
      onSaved()
    } catch (error) {
      notifyError(error, '保存失败,请重试')
    } finally {
      setIsSubmitting(false)
    }
  }

  const goalConfig = {
    marriage: { icon: Heart, color: 'text-rose', bgColor: 'bg-rose-soft' },
    dating: { icon: Sparkles, color: 'text-gold', bgColor: 'bg-gold-soft' },
    friends: { icon: Users, color: 'text-primary', bgColor: 'bg-primary/10' },
  }

  if (isLoading) {
    return (
      <SlideInTransition direction="left" className="min-h-screen bg-background">
        <div className="flex items-center justify-center h-full">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
        </div>
      </SlideInTransition>
    )
  }

  return (
    <SlideInTransition direction="left" className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/20 via-background to-background pointer-events-none" />
        <div className="grain-texture absolute inset-0" />
      </div>

      {/* Header */}
      <header className="relative z-10">
        <PageHeader
          title="编辑资料"
          showBack
          onBack={onBack}
        />
      </header>

      {/* Content */}
      <div
        ref={contentRef}
        className="relative z-10 flex-1 flex flex-col px-6 pt-6 overflow-y-auto scrollbar-hide"
      >
        {/* Validation errors */}
        {validationErrors.length > 0 && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-destructive/10 border border-destructive/20 animate-fade-in-up">
            <p className="text-sm text-destructive">
              {validationErrors.join('、')}
            </p>
          </div>
        )}

        {/* Photo Upload Card */}
        <div className="rounded-2xl border-2 border-dashed border-border p-6 bg-card/50 mb-6">
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
              'block text-center mb-4 transition-opacity cursor-pointer',
              isUploading || profile.photos.length >= 6 ? 'opacity-60 cursor-default' : ''
            )}
          >
            <h3 className="font-medium text-foreground mb-1">照片</h3>
            <p className="text-sm text-muted-foreground">最多可上传6张</p>
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
              <label
                htmlFor={photoInputId}
                aria-label="添加照片"
                className={cn(
                  'w-20 h-20 rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-1 transition-all cursor-pointer',
                  isUploading
                    ? 'border-muted opacity-60 cursor-not-allowed'
                    : 'border-border text-muted-foreground hover:border-primary hover:text-primary'
                )}
              >
                {isUploading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <ImagePlus className="w-5 h-5" />
                    <span className="text-xs">添加</span>
                  </>
                )}
              </label>
            )}
          </div>
        </div>

        {/* Basic Info */}
        <div className="space-y-5">
          {/* Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium mb-2 text-foreground">
              名字
            </label>
            <input
              id="name"
              type="text"
              value={profile.name}
              onChange={(e) => setProfile({ ...profile, name: e.target.value })}
              placeholder="怎么称呼你"
              className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
              autoComplete="off"
              maxLength={50}
            />
          </div>

          {/* Gender */}
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

          {/* Sexual Orientation */}
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

          {/* Birthday */}
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

          {/* City */}
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

          {/* Relationship Goal */}
          <div>
            <label className="block text-sm font-medium mb-3 text-foreground">
              关系目标
            </label>
            <div className="space-y-3">
              {[
                { value: 'marriage', title: '奔着结婚去', desc: '目标明确，希望认真推进' },
                { value: 'dating', title: '先谈恋爱看', desc: '先看相处和感觉，再决定往哪里走' },
                { value: 'friends', title: '找搭子 / 扩列', desc: '先认识合拍的人，轻松一点开始' },
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
                      'w-full p-4 rounded-2xl text-left transition-all duration-200 border-2 focus-ring relative',
                      isSelected
                        ? 'bg-primary/5 border-primary shadow-sm scale-[1.01]'
                        : 'bg-card border-border hover:border-primary/30 active:scale-[0.99]'
                    )}
                    aria-pressed={isSelected}
                  >
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-all',
                        isSelected ? config.bgColor : 'bg-secondary'
                      )}>
                        <IconComponent className={cn(
                          'w-5 h-5 transition-colors',
                          isSelected ? config.color : 'text-muted-foreground'
                        )} />
                      </div>
                      <div className="flex-1 pr-6">
                        <div className={cn(
                          'font-semibold text-sm mb-0.5 transition-colors',
                          isSelected ? 'text-primary' : 'text-foreground'
                        )}>
                          {option.title}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {option.desc}
                        </div>
                      </div>
                      {isSelected && (
                        <span className="absolute right-3 top-1/2 -translate-y-1/2">
                          <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                            <Check className="w-3 h-3 text-primary-foreground" />
                          </div>
                        </span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="py-6 safe-area-bottom">
          <Button
            onClick={() => void handleSave()}
            disabled={isSubmitting}
            className={cn(
              'w-full h-12 rounded-2xl text-base transition-all duration-200',
              !isSubmitting ? 'shadow-lg shadow-primary/20' : ''
            )}
            size="lg"
          >
            {isSubmitting ? '保存中…' : '保存修改'}
          </Button>
        </div>
      </div>
    </SlideInTransition>
  )
}