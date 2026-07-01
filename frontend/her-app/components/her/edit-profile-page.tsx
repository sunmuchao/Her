'use client'

import { useState, useRef, useEffect, useId } from 'react'
import { X, Check, ImagePlus, Heart, Users, Sparkles, Loader2, User, Briefcase, Home, Target } from 'lucide-react'
import { cn } from '@/lib/utils'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { applyLoginPayload } from '@/lib/auth/session'
import { notifyError, notifySuccess } from '@/lib/notify'
import { Button } from '@/components/ui/button'
import { CitySelector } from '@/components/her/ui/city-selector'
import { DateWheelPicker } from '@/components/her/ui/date-wheel-picker'
import { CollapsibleCard } from '@/components/her/ui/collapsible-card'
import { NumberInputWithUnit } from '@/components/her/ui/number-input-with-unit'
import { SelectDropdown } from '@/components/her/ui/select-dropdown'
import { useProfilePageData } from '@/lib/hooks/use-profile-page-data'
import { PageHeader } from '@/components/her/ui/page-header'
import { SlideInTransition } from '@/components/her/ui/page-transitions'

interface EditProfilePageProps {
  onBack: () => void
  onSaved: () => void
}

interface ProfileData {
  // 已有字段（9个）
  name: string
  gender: string
  sexualOrientation: string
  birthday: string
  currentCity: string
  photos: string[]
  relationshipGoal: string
  marriageStatus: string
  hasChildren: string

  // 新增字段（15个）
  height: number | null          // 身高（cm）
  weight: number | null          // 体重（kg）
  education: string | null       // 学历
  job: string | null             // 职业
  incomeRange: string | null     // 收入范围
  hometownCity: string | null    // 籍贯城市
  childrenCount: number | null   // 孩子数量
  childrenLivingWithSelf: string | null // 孩子是否随自己
  smoking: string | null         // 抽烟情况
  drinking: string | null        // 喝酒情况
  hasHouse: string | null        // 房产情况
  hasCar: string | null          // 车产情况
  religion: string | null        // 宗教信仰
  isOnlyChild: string | null     // 是否独生子女
  district: string | null        // 区县
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }
  return ''
}

function firstStringArray(...values: unknown[]): string[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      const normalized = value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      if (normalized.length > 0) {
        return normalized
      }
    }
  }
  return []
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && !isNaN(value)) {
      return value
    }
    if (typeof value === 'string') {
      const parsed = parseInt(value, 10)
      if (!isNaN(parsed)) {
        return parsed
      }
    }
  }
  return null
}

function firstBool(...values: unknown[]): string | null {
  for (const value of values) {
    if (value === true || value === 1 || value === '1' || value === 'yes') return 'yes'
    if (value === false || value === 0 || value === '0' || value === 'no') return 'no'
  }
  return null
}

function normalizeBooleanChoice(value: unknown): string {
  if (value === 'yes' || value === 'no') return value
  if (value === true || value === 1 || value === '1') return 'yes'
  if (value === false || value === 0 || value === '0') return 'no'
  if (typeof value === 'string') {
    if (['有', '是', 'yes', 'true'].includes(value.toLowerCase())) return 'yes'
    if (['没有', '否', 'no', 'false'].includes(value.toLowerCase())) return 'no'
  }
  return ''
}

function normalizeGender(value: unknown): string {
  if (value === 'male' || value === 'female') return value
  if (value === '男') return 'male'
  if (value === '女') return 'female'
  return ''
}

function normalizeRelationshipGoal(value: unknown): string {
  if (value === 'marriage' || value === 'dating' || value === 'friends') return value
  if (typeof value !== 'string') return ''
  if (value.includes('结婚')) return 'marriage'
  if (value.includes('恋爱')) return 'dating'
  if (value.includes('搭子') || value.includes('扩列') || value.includes('朋友')) return 'friends'
  return ''
}

function normalizeMarriageStatus(value: unknown): string {
  if (value === 'never_married' || value === 'divorced' || value === 'widowed') return value
  if (typeof value !== 'string') return ''
  if (value.includes('未婚')) return 'never_married'
  if (value.includes('离异') || value.includes('离婚')) return 'divorced'
  if (value.includes('丧偶')) return 'widowed'
  return ''
}

function normalizeOrientation(value: unknown): string {
  if (value === 'like_male' || value === 'like_female' || value === 'both') return value
  if (typeof value !== 'string') return ''
  if (value.includes('男')) return 'like_male'
  if (value.includes('女')) return 'like_female'
  if (value.includes('都')) return 'both'
  return ''
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
    // 已有字段初始值
    name: '',
    gender: '',
    sexualOrientation: '',
    birthday: '',
    currentCity: '',
    photos: [],
    relationshipGoal: '',
    marriageStatus: '',
    hasChildren: '',

    // 新增字段初始值
    height: null,
    weight: null,
    education: null,
    job: null,
    incomeRange: null,
    hometownCity: null,
    childrenCount: null,
    childrenLivingWithSelf: null,
    smoking: null,
    drinking: null,
    hasHouse: null,
    hasCar: null,
    religion: null,
    isOnlyChild: null,
    district: null,
  })

  // 数据加载完成后初始化表单
  useEffect(() => {
    if (!isLoading && (auth || facts)) {
      const rawProfile = facts?.profile_facts ?? {}
      const user = auth?.user ?? {}
      const onboardingBasicInfo = auth?.onboarding?.basic_info ?? {}
      const authProfile = auth?.profile ?? {}

      setProfile({
        // 已有字段...
        name: firstString(
          rawProfile.name,
          onboardingBasicInfo.name,
          authProfile.name,
          user.display_name,
        ),
        gender: normalizeGender(
          rawProfile.gender,
        ) || normalizeGender(onboardingBasicInfo.gender) || normalizeGender(authProfile.gender),
        sexualOrientation:
          normalizeOrientation(rawProfile.sexual_orientation) ||
          normalizeOrientation(onboardingBasicInfo.sexual_orientation) ||
          normalizeOrientation(authProfile.sexual_orientation),
        birthday: firstString(
          rawProfile.birthday,
          onboardingBasicInfo.birthday,
          authProfile.birthday,
        ),
        currentCity: firstString(
          rawProfile.city,
          rawProfile.settlement_city,
          onboardingBasicInfo.city,
          onboardingBasicInfo.location,
          authProfile.city,
          authProfile.settlement_city,
        ),
        photos: [
          ...firstStringArray(rawProfile.photos, authProfile.photos),
          ...firstStringArray(rawProfile.photo_urls, authProfile.photo_urls),
          ...(() => {
            const avatar = firstString(rawProfile.avatar_url, authProfile.avatar_url, user.avatar_url)
            return avatar ? [avatar] : []
          })(),
        ].filter((photo, index, arr) => arr.indexOf(photo) === index).slice(0, 6),
        relationshipGoal:
          normalizeRelationshipGoal(rawProfile.relationship_goal) ||
          normalizeRelationshipGoal(onboardingBasicInfo.relationship_goal) ||
          normalizeRelationshipGoal(authProfile.relationship_goal),
        marriageStatus:
          normalizeMarriageStatus(rawProfile.marital_status) ||
          normalizeMarriageStatus(rawProfile.marriage_status) ||
          normalizeMarriageStatus(onboardingBasicInfo.marriage_status) ||
          normalizeMarriageStatus(authProfile.marital_status) ||
          normalizeMarriageStatus(authProfile.marriage_status),
        hasChildren:
          normalizeBooleanChoice(rawProfile.has_children) ||
          normalizeBooleanChoice(rawProfile.parenting_status) ||
          normalizeBooleanChoice(onboardingBasicInfo.has_children) ||
          normalizeBooleanChoice(authProfile.has_children) ||
          normalizeBooleanChoice(authProfile.parenting_status),

        // 新增字段：从 rawProfile 和 authProfile 合并
        height: firstNumber(rawProfile.self_height, rawProfile.height, authProfile.height),
        weight: firstNumber(rawProfile.weight, authProfile.weight),
        education: firstString(rawProfile.self_education, rawProfile.education, authProfile.education),
        job: firstString(rawProfile.self_job, rawProfile.job, authProfile.job),
        incomeRange: firstString(rawProfile.self_income_wan, rawProfile.income_range, authProfile.income_range, onboardingBasicInfo.income_range),
        hometownCity: firstString(rawProfile.hometown_city, authProfile.hometown_city, onboardingBasicInfo.hometown_city),
        childrenCount: firstNumber(rawProfile.self_children_count, rawProfile.children_count, authProfile.children_count, onboardingBasicInfo.children_count),
        childrenLivingWithSelf: firstBool(rawProfile.self_children_living_with_self, rawProfile.children_living_with_self, authProfile.children_living_with_self, onboardingBasicInfo.children_living_with_self),
        smoking: firstString(rawProfile.self_smoking, rawProfile.smoking, authProfile.smoking, onboardingBasicInfo.smoking),
        drinking: firstString(rawProfile.self_drinking, rawProfile.drinking, authProfile.drinking, onboardingBasicInfo.drinking),
        hasHouse: firstString(rawProfile.has_house, authProfile.has_house, onboardingBasicInfo.has_house),
        hasCar: firstString(rawProfile.has_car, authProfile.has_car, onboardingBasicInfo.has_car),
        religion: firstString(rawProfile.religion, authProfile.religion, onboardingBasicInfo.religion),
        isOnlyChild: firstBool(rawProfile.is_only_child, authProfile.is_only_child, onboardingBasicInfo.is_only_child),
        district: firstString(rawProfile.self_district, rawProfile.district, authProfile.district, onboardingBasicInfo.district),
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

    // 新增验证
    if (profile.height && (profile.height < 100 || profile.height > 250)) {
      errors.push('身高需在100-250cm之间')
    }
    if (profile.weight && (profile.weight < 30 || profile.weight > 200)) {
      errors.push('体重需在30-200kg之间')
    }
    if (profile.job && profile.job.length > 30) {
      errors.push('职业最长30字符')
    }
    if (profile.childrenCount && (profile.childrenCount < 0 || profile.childrenCount > 10)) {
      errors.push('孩子数量需在0-10之间')
    }
    if (profile.hasChildren === 'yes' && !profile.childrenCount) {
      errors.push('有孩子时需填写孩子数量')
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
          // 已有字段...
          name: profile.name,
          birthday: profile.birthday,
          gender: profile.gender,
          sexual_orientation: profile.sexualOrientation,
          location: profile.currentCity,
          city: profile.currentCity,
          relationship_goal: profile.relationshipGoal,
          marriage_status: profile.marriageStatus,
          has_children: profile.hasChildren,

          // 新增字段：添加到 basic_info
          height: profile.height,
          weight: profile.weight,
          education: profile.education,
          job: profile.job,
          income_range: profile.incomeRange,
          hometown_city: profile.hometownCity,
          children_count: profile.childrenCount,
          children_living_with_self: profile.childrenLivingWithSelf,
          smoking: profile.smoking,
          drinking: profile.drinking,
          has_house: profile.hasHouse,
          has_car: profile.hasCar,
          religion: profile.religion,
          is_only_child: profile.isOnlyChild,
          district: profile.district,
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

        {/* 卡片1：照片展示 */}
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

        {/* 卡片2：基本信息 */}
        <CollapsibleCard
          title="基本信息"
          icon={<User className="w-4 h-4" />}
          defaultExpanded={true}
          className="mb-4"
        >
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

          {/* District */}
          <div>
            <label htmlFor="district" className="block text-sm font-medium mb-2 text-foreground">
              区县
            </label>
            <input
              id="district"
              type="text"
              value={profile.district || ''}
              onChange={(e) => setProfile({ ...profile, district: e.target.value })}
              placeholder="如：朝阳区"
              className="w-full px-4 py-3.5 rounded-xl text-base outline-none transition-all bg-input border-2 border-border text-foreground placeholder:text-muted-foreground focus:border-primary focus:ring-1 focus:ring-primary"
              autoComplete="off"
            />
          </div>
        </CollapsibleCard>
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
