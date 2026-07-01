'use client'

import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import {
  Settings,
  ChevronRight,
  BadgeCheck,
  MapPin,
  Edit3,
  Shield,
  X,
  Plus,
  Video,
  UserCheck,
  GraduationCap,
  Briefcase,
  Wallet,
} from 'lucide-react'
import Image from 'next/image'
import { useProfilePageData } from '@/lib/hooks/use-profile-page-data'
import { buildProfileView, calculateVerificationProgress } from '@/lib/mappers/profile-view'
import { patchPersonaTags } from '@/lib/api/endpoints/persona'
import { submitOnboarding } from '@/lib/auth/auth-api'
import { cn } from '@/lib/utils'
import { ProgressRing } from './ui/progress-ring'
import { FadeIn, PageTransition } from './ui/animations'
import { ThemeToggle } from './ui/theme-toggle'
import { DemoDataBanner } from './ui/demo-data-banner'
import { PageErrorState } from './ui/error-handling'
import { PageHeader } from './ui/page-header'
import { ProfilePageSkeleton } from './ui/skeletons/profile-skeleton'

interface ProfilePageProps {
  onStartVerification: (from?: 'profile', target?: string) => void
  onOpenOnboarding?: () => void
  onOpenEditProfile?: () => void
  onOpenSettings?: () => void
}

/**
 * Profile 页面 - 个人中心主页
 *
 * 使用 React Query hooks 管理数据获取，组件只负责渲染
 */
export default function ProfilePage({
  onStartVerification,
  onOpenOnboarding,
  onOpenEditProfile,
  onOpenSettings,
}: ProfilePageProps) {
  const defaultHeadline = '认真关系，从认真了解开始'
  const onboardingHeadline = '登录后完善你的资料'

  // 使用聚合数据 hook
  const { auth, facts, collected, trust, isLoading, error, queries, refetch } = useProfilePageData()

  // 标签编辑状态
  const [isEditingTags, setIsEditingTags] = useState(false)
  const [editedTags, setEditedTags] = useState<string[]>([])
  const [isAddingTag, setIsAddingTag] = useState(false)
  const [newTagInput, setNewTagInput] = useState('')
  const [editingTagIndex, setEditingTagIndex] = useState<number | null>(null)
  const [editingTagValue, setEditingTagValue] = useState('')
  const [isSavingTags, setIsSavingTags] = useState(false)
  const [isEditingHeadline, setIsEditingHeadline] = useState(false)
  const [headlineDraft, setHeadlineDraft] = useState('')
  const [isSavingHeadline, setIsSavingHeadline] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const editInputRef = useRef<HTMLInputElement>(null)
  const headlineTextareaRef = useRef<HTMLTextAreaElement>(null)
  const tagsAreaRef = useRef<HTMLDivElement>(null)

  // 构建视图数据
  const profile = useMemo(
    () => buildProfileView(auth, facts, collected, trust),
    [auth, facts, collected, trust],
  )

  // 进入编辑模式（单击触发）
  const handleEnterEdit = () => {
    if (isSavingTags) return
    setEditedTags([...profile.tags])
    setIsEditingTags(true)
    setIsAddingTag(false)
    setNewTagInput('')
    setEditingTagIndex(null)
    setEditingTagValue('')
  }

  // 点击标签进入编辑
  const handleEditTag = (index: number) => {
    setEditingTagIndex(index)
    setEditingTagValue(editedTags[index])
    setTimeout(() => {
      editInputRef.current?.focus()
    }, 50)
  }

  // 确认编辑标签
  const handleConfirmEditTag = () => {
    const trimmed = editingTagValue.trim().slice(0, 20)
    if (trimmed && editingTagIndex !== null) {
      const newTags = [...editedTags]
      // 检查是否与其他标签重复
      if (!newTags.some((t, i) => i !== editingTagIndex && t === trimmed)) {
        newTags[editingTagIndex] = trimmed
        setEditedTags(newTags)
      }
    }
    setEditingTagIndex(null)
    setEditingTagValue('')
  }

  // 编辑标签键盘事件
  const handleEditTagKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleConfirmEditTag()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setEditingTagIndex(null)
      setEditingTagValue('')
    }
  }

  // 添加新标签
  const handleAddTag = () => {
    if (editedTags.length >= 6) return
    setIsAddingTag(true)
    setNewTagInput('')
    // 自动聚焦输入框
    setTimeout(() => {
      inputRef.current?.focus()
    }, 50)
  }

  // 确认添加标签
  const handleConfirmAddTag = () => {
    const trimmed = newTagInput.trim().slice(0, 20)
    if (trimmed && !editedTags.includes(trimmed) && editedTags.length < 6) {
      setEditedTags([...editedTags, trimmed])
    }
    setIsAddingTag(false)
    setNewTagInput('')
    // 保持编辑模式，不退出
  }

  // 删除标签
  const handleRemoveTag = (index: number) => {
    const newTags = [...editedTags]
    newTags.splice(index, 1)
    setEditedTags(newTags)
  }

  // 保存并退出编辑
  const handleSaveAndExit = useCallback(async (currentTags: string[]) => {
    setIsEditingTags(false)
    setIsAddingTag(false)
    setNewTagInput('')
    setEditingTagIndex(null)
    setEditingTagValue('')
    setIsSavingTags(true)

    try {
      await patchPersonaTags(currentTags)
      await refetch()
    } catch (e) {
      console.error('保存标签失败:', e)
    } finally {
      setIsSavingTags(false)
    }
  }, [refetch])

  const handleEnterHeadlineEdit = useCallback(() => {
    if (isSavingHeadline) return
    setHeadlineDraft(
      profile.headline === onboardingHeadline || profile.headline === defaultHeadline
        ? ''
        : profile.headline,
    )
    setIsEditingHeadline(true)
    setTimeout(() => {
      headlineTextareaRef.current?.focus()
      headlineTextareaRef.current?.setSelectionRange(
        headlineTextareaRef.current.value.length,
        headlineTextareaRef.current.value.length,
      )
    }, 50)
  }, [defaultHeadline, isSavingHeadline, onboardingHeadline, profile.headline])

  const handleSaveHeadline = useCallback(async () => {
    const trimmed = headlineDraft.trim().slice(0, 80)
    setIsEditingHeadline(false)

    if (
      trimmed === profile.headline ||
      (!trimmed && (profile.headline === onboardingHeadline || profile.headline === defaultHeadline))
    ) {
      setHeadlineDraft(trimmed)
      return
    }

    setIsSavingHeadline(true)
    try {
      await submitOnboarding({
        basic_info: {
          public_notes: trimmed,
        },
        mark_completed: false,
      })
      await refetch()
    } catch (error) {
      console.error('保存个人简介失败:', error)
      setHeadlineDraft(profile.headline)
    } finally {
      setIsSavingHeadline(false)
    }
  }, [defaultHeadline, headlineDraft, onboardingHeadline, profile.headline, refetch])

  const handleHeadlineKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      void handleSaveHeadline()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setIsEditingHeadline(false)
      setHeadlineDraft(profile.headline)
    }
  }, [handleSaveHeadline, profile.headline])

  // 点击外部区域自动保存并退出
  useEffect(() => {
    if (!isEditingTags) return

    const handleClickOutside = (e: MouseEvent) => {
      if (tagsAreaRef.current && !tagsAreaRef.current.contains(e.target as Node)) {
        // 先确认正在编辑的内容
        const finalTags = [...editedTags]
        if (editingTagIndex !== null && editingTagValue.trim()) {
          const trimmed = editingTagValue.trim().slice(0, 20)
          if (!finalTags.some((t, i) => i !== editingTagIndex && t === trimmed)) {
            finalTags[editingTagIndex] = trimmed
          }
        }
        if (isAddingTag && newTagInput.trim()) {
          const trimmed = newTagInput.trim().slice(0, 20)
          if (!finalTags.includes(trimmed) && finalTags.length < 6) {
            finalTags.push(trimmed)
          }
        }
        handleSaveAndExit(finalTags)
      }
    }

    // 延迟添加监听，避免进入编辑的点击立即触发退出
    const timer = setTimeout(() => {
      document.addEventListener('click', handleClickOutside)
    }, 200)

    return () => {
      clearTimeout(timer)
      document.removeEventListener('click', handleClickOutside)
    }
  }, [isEditingTags]) // 只依赖 isEditingTags，避免循环

  // 处理输入框键盘事件
  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleConfirmAddTag()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setIsAddingTag(false)
      setNewTagInput('')
    }
  }

  const { progress: verificationProgress } = useMemo(
    () => calculateVerificationProgress(profile.verificationItems),
    [profile.verificationItems],
  )
  const verificationPriorityMap: Record<string, { order: number; target?: string; icon: React.ElementType }> = {
    '活体视频认证': { order: 0, target: 'video', icon: Video },
    '真人认证': { order: 0, target: 'video', icon: Video },
    '身份认证': { order: 1, icon: UserCheck },
    '学历认证': { order: 2, target: 'education', icon: GraduationCap },
    '职业认证': { order: 3, target: 'occupation', icon: Briefcase },
    '收入认证': { order: 4, target: 'income', icon: Wallet },
  }
  const verificationItems = useMemo(
    () =>
      [...profile.verificationItems].sort((a, b) => {
        const aPriority = verificationPriorityMap[a.name]?.order ?? 99
        const bPriority = verificationPriorityMap[b.name]?.order ?? 99
        if (aPriority !== bPriority) return aPriority - bPriority
        if (a.status !== b.status) return a.status === 'unverified' ? -1 : 1
        return a.name.localeCompare(b.name, 'zh-CN')
      }),
    [profile.verificationItems],
  )
  const hasCompletedAllVerifications = verificationItems.length > 0 && verificationItems.every((item) => item.status === 'verified')
  const verificationCardTitle = hasCompletedAllVerifications
    ? '已完成全部认证'
    : '我的认证'
  const verificationCardDescription = hasCompletedAllVerifications
    ? '全部认证已完成'
    : '点任一卡片直接去对应认证页'

  // 判断是否使用 Mock 数据
  const usingMockData = useMemo(() => {
    return queries.auth.data?.user?.user_id === 'demo-user'
  }, [queries.auth.data])

  // 加载状态
  if (isLoading) {
    return <ProfilePageSkeleton />
  }

  // 错误状态
  if (error) {
    return (
      <PageErrorState
        message={error}
        onRetry={() => queries.auth.refetch()}
        variant="full"
      />
    )
  }

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {usingMockData && <DemoDataBanner />}

      {/* Header - 使用统一组件 */}
      <PageHeader
        title="我的"
        rightActions={
          <div className="flex items-center gap-2">
            <ThemeToggle size="sm" />
            <button
              type="button"
              onClick={onOpenSettings}
              className="w-8 h-8 flex items-center justify-center focus-ring rounded-full hover:bg-secondary/50 transition-colors"
              aria-label="设置"
            >
              <Settings className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {/* 用户资料卡片 */}
        <FadeIn delay={100}>
          <section className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="relative">
                <div className="w-16 h-16 rounded-full overflow-hidden">
                  <Image
                    src={profile.avatar}
                    alt={profile.name}
                    width={64}
                    height={64}
                    className="object-cover"
                  />
                </div>
                {profile.verified && (
                  <BadgeCheck
                    className="absolute -bottom-0.5 -right-0.5 w-5 h-5 text-primary bg-background rounded-full"
                    aria-label="已认证"
                  />
                )}
              </div>
              <div>
                <h2 className="font-medium">
                  {profile.name}
                  {profile.age ? `，${profile.age}` : ''}
                </h2>
                <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3 h-3" aria-hidden="true" />
                    {profile.city}
                  </span>
                  <span>{profile.occupation}</span>
                </div>
              </div>
            </div>
            {isEditingHeadline ? (
              <textarea
                ref={headlineTextareaRef}
                value={headlineDraft}
                onChange={(e) => setHeadlineDraft(e.target.value)}
                onBlur={() => void handleSaveHeadline()}
                onKeyDown={handleHeadlineKeyDown}
                rows={3}
                maxLength={80}
                placeholder="写一句介绍自己"
                className="w-full mb-3 resize-none rounded-lg border border-primary bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary"
              />
            ) : (
              <button
                type="button"
                onClick={handleEnterHeadlineEdit}
                className="mb-3 block w-full rounded-lg text-left text-sm text-muted-foreground transition-colors hover:bg-secondary/40 px-2 py-2 -mx-2"
                aria-label="编辑个人简介"
              >
                {isSavingHeadline ? '保存中...' : profile.headline}
              </button>
            )}

            {/* 标签区域 - 点击编辑 */}
            <div
              ref={tagsAreaRef}
              className={cn(
                'flex flex-wrap gap-1.5 items-center min-h-[28px]',
                !isEditingTags && 'cursor-pointer',
              )}
              onClick={!isEditingTags ? handleEnterEdit : undefined}
            >
              {isEditingTags ? (
                <>
                  {/* 编辑模式：显示标签+删除按钮 */}
                  {editedTags.map((tag, i) => (
                    editingTagIndex === i ? (
                      // 正在编辑的标签显示输入框
                      <input
                        key={`edit-${i}`}
                        ref={editInputRef}
                        type="text"
                        value={editingTagValue}
                        onChange={(e) => setEditingTagValue(e.target.value)}
                        onKeyDown={handleEditTagKeyDown}
                        onMouseDown={(e) => e.stopPropagation()}
                        onBlur={handleConfirmEditTag}
                        placeholder="输入..."
                        maxLength={20}
                        autoFocus
                        className="w-[80px] px-2 py-1 text-xs bg-background border border-primary rounded-md outline-none"
                      />
                    ) : (
                      // 普通标签：点击可编辑
                      <span
                        key={`${tag}-${i}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleEditTag(i)
                        }}
                        className="inline-flex items-center gap-1 px-2 py-1 bg-secondary text-xs text-muted-foreground rounded-md cursor-pointer hover:bg-secondary/80 transition-colors"
                      >
                        {tag}
                        <button
                          type="button"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleRemoveTag(i)
                          }}
                          className="w-4 h-4 flex items-center justify-center hover:text-destructive transition-colors"
                          aria-label={`删除标签 ${tag}`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    )
                  ))}

                  {/* 加号按钮或输入框 */}
                  {isAddingTag ? (
                    <input
                      ref={inputRef}
                      type="text"
                      value={newTagInput}
                      onChange={(e) => setNewTagInput(e.target.value)}
                      onKeyDown={handleInputKeyDown}
                      onMouseDown={(e) => e.stopPropagation()}
                      placeholder="输入..."
                      maxLength={20}
                      autoFocus
                      className="w-[80px] px-2 py-1 text-xs bg-background border border-primary rounded-md outline-none"
                    />
                  ) : (
                    editedTags.length < 6 && (
                      <button
                        type="button"
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleAddTag()
                        }}
                        className="w-6 h-6 flex items-center justify-center bg-primary/10 hover:bg-primary/20 text-primary rounded-md transition-colors"
                        aria-label="添加标签"
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    )
                  )}
                </>
              ) : (
                <>
                  {/* 展示模式：只显示标签 */}
                  {profile.tags.length > 0 ? (
                    profile.tags.map((tag, i) => (
                      <span
                        key={i}
                        className="px-2 py-1 bg-secondary text-xs text-muted-foreground rounded-md"
                      >
                        {tag}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground/50 italic">点击添加标签</span>
                  )}
                </>
              )}
            </div>
          </section>
        </FadeIn>

        {/* 认证状态 */}
        <FadeIn delay={200}>
          <section>
            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center gap-3 mb-3">
                <ProgressRing progress={verificationProgress} size={48} strokeWidth={4} color="rose">
                  <Shield className="w-5 h-5 text-primary" />
                </ProgressRing>
                <div className="flex-1">
                  <p className="text-xs text-primary font-medium mb-1">认证情况</p>
                  <h3 className="font-medium">{verificationCardTitle}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{verificationCardDescription}</p>
                </div>
              </div>

              {verificationItems.length > 0 ? (
                <div className="grid grid-cols-4 gap-3">
                  {verificationItems.map((item, i) => {
                    const config = verificationPriorityMap[item.name]
                    const target = config?.target
                    const Icon = config?.icon || Shield
                    const actionable = item.status !== 'verified' && Boolean(target)
                    
                    return (
                      <button
                        key={`${item.name}-${i}`}
                        type="button"
                        onClick={() => {
                          if (!actionable || !target) return
                          onStartVerification('profile', target)
                        }}
                        disabled={!actionable}
                        className={cn(
                          'flex flex-col items-center gap-1.5 py-3 rounded-lg transition-colors',
                          actionable && 'active:scale-95',
                        )}
                      >
                        {/* 图标容器 */}
                        <div className={cn(
                          'w-12 h-12 rounded-full flex items-center justify-center transition-colors',
                          item.status === 'verified'
                            ? 'bg-primary/10'
                            : item.status === 'pending'
                              ? 'bg-gold/10'
                              : 'bg-secondary',
                        )}>
                          <Icon className={cn(
                            'w-5 h-5',
                            item.status === 'verified'
                              ? 'text-primary'
                              : item.status === 'pending'
                                ? 'text-gold'
                                : 'text-muted-foreground',
                          )} />
                        </div>
                        
                        {/* 认证名称 */}
                        <span className="text-xs text-foreground font-medium truncate max-w-full px-1">
                          {item.name.replace('认证', '')}
                        </span>
                        
                        {/* 认证状态 */}
                        <span className={cn(
                          'text-[10px]',
                          item.status === 'verified'
                            ? 'text-primary'
                            : item.status === 'pending'
                              ? 'text-gold'
                              : 'text-muted-foreground',
                        )}>
                          {item.status === 'verified' ? '已认证' : item.status === 'pending' ? '审核中' : '未认证'}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">暂无认证项</p>
              )}
            </div>
          </section>
        </FadeIn>

        {/* 操作入口 */}
        <FadeIn delay={300}>
          <section className="bg-card border border-border rounded-xl overflow-hidden">
            {[
              { icon: Edit3, label: '编辑资料', onClick: onOpenEditProfile || onOpenOnboarding },
            ].map((item) => {
              const Icon = item.icon
              if (!item.onClick) return null
              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={item.onClick}
                  className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-secondary/50 transition-colors focus-ring"
                  aria-label={item.label}
                >
                  <Icon className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
                  <span className="flex-1 text-sm">{item.label}</span>
                  <ChevronRight className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                </button>
              )
            })}
          </section>
        </FadeIn>
      </div>
    </PageTransition>
  )
}
