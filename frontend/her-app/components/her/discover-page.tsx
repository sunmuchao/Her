'use client'

import { useState, useEffect, useRef } from 'react'
import { ArrowLeft, BadgeCheck, ChevronDown, ImagePlus, Mic, Plus, Search, Send, X, Brain, Heart, Sparkles, ClipboardList, Coins, History, Star, UserRoundSearch } from 'lucide-react'
import { AssessmentCardRenderer } from '@/components/assessment/AssessmentCardRenderer'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
import Image from 'next/image'
import { EmptyRecommendations, EmptySearchResults } from './ui/empty-states'
import { InboxItemSkeleton, DiscoverPageSkeleton } from './ui/skeletons'
import { TypingIndicator } from './ui/typing-indicator'
import { OnlineIndicator } from './ui/animations'
import { SwipeToDelete } from './ui/swipe-to-delete'
import { DiscoveryCandidateCard } from './discovery-candidate-card'
import { DiscoveryProfileUpdatePrompt } from './discovery-profile-update-prompt'
import { DiscoverySessionList } from './discovery-session-list'
import type { DiscoveryTimelineItem } from '@/lib/discovery/map-discovery-view'
import { cn } from '@/lib/utils'
import { getAccessToken, getProfileId, getUserId } from '@/lib/auth/session'
import { confirmSessionOrRedirectToWelcome } from '@/lib/auth/confirm-session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError } from '@/lib/notify'
import { toast } from 'sonner'
import { EMPTY_PREFS_PLACEHOLDER } from '@/lib/fixtures/demo-profiles'
import type { CandidatePreview } from '@/lib/types/candidate'
import { useDiscoverySession } from '@/hooks/use-discovery-session'
import { useVoiceInput } from '@/hooks/use-voice-input'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { XiaoyaRichText } from './ui/xiaoya-rich-text'
import {
  answerAssessment,
  beginAssessment,
  startAssessment,
  getXiaoyaMessage,
  addAssessmentLabels,
  addXiaoyaMessageToDiscovery,
  type AssessmentCard,
  type AssessmentQuestionCard,
} from '@/lib/api/endpoints/assessment'
import {
  getValuesAuctionInterpretation,
  getValuesAuctionLots,
  startValuesAuction,
  submitValuesAuctionBids,
  type ValuesAuctionCard,
} from '@/lib/api/endpoints/valuesAuction'
import { ValuesAuctionCardRenderer } from '@/components/values-auction'
import { useSearchParams } from 'next/navigation'
import { searchDiscoveryByPhoto, type DiscoveryPhotoSearchMode } from '@/lib/api/endpoints/discovery'
import { fetchRecommendationCards, markRecommendationCardsRead } from '@/lib/api/endpoints/recommendation'
import { isAuthRequiredGatewayError } from '@/lib/api/errors'

const PSYCHOLOGY_XIAOYA_RESULT_DELAY_MS = 2000

function waitForPsychologyXiaoyaResult() {
  return new Promise((resolve) => {
    window.setTimeout(resolve, PSYCHOLOGY_XIAOYA_RESULT_DELAY_MS)
  })
}

async function compressPhotoSearchImage(file: File, maxWidth = 1280, quality = 0.82): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (event) => {
      const img = new window.Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        let width = img.width
        let height = img.height
        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width)
          width = maxWidth
        }
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          reject(new Error('图片预处理失败'))
          return
        }
        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.onerror = () => reject(new Error('图片解析失败'))
      img.src = String(event.target?.result || '')
    }
    reader.onerror = () => reject(new Error('图片读取失败'))
    reader.readAsDataURL(file)
  })
}

interface DiscoverPageProps {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null) => void
  onSessionIdChange?: (sessionId: string | null) => void
}

function DiscoveryTimelineEntry({
  item,
  sessionId,
  onViewCandidate,
  onProfileUpdateResolved,
  onAddLabels,
  onSubmitAction,
  onOpenAssessment,
  isSubmittingTurn,
}: {
  item: DiscoveryTimelineItem
  sessionId: string | null
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null) => void
  onProfileUpdateResolved?: () => void
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
  onSubmitAction?: (actionId: string) => void
  onOpenAssessment?: (assessmentType: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love') => void
  isSubmittingTurn?: boolean
}) {
  // DEBUG: 验证渲染时的 item 数据
  console.log('[DEBUG DiscoveryTimelineEntry] 渲染 item:', item.kind, 'id=', item.id)
  if (item.kind === 'result_group') {
    console.log('[DEBUG DiscoveryTimelineEntry] result_group candidates:', item.candidates.length)
    item.candidates.forEach((c, idx) => {
      console.log(`  candidate[${idx}]: id=${c.id}, name=${c.name}`)
    })
  }

  if (item.kind === 'profile_update_prompt') {
    if (!sessionId) return null
    return (
      <DiscoveryProfileUpdatePrompt
        sessionId={sessionId}
        item={item}
        onResolved={() => onProfileUpdateResolved?.()}
      />
    )
  }

  if (item.kind === 'assessment_result') {
    // 从卡片中提取 assessment_type
    const cardAssessmentType = (
      item.card && 'assessment_type' in item.card ? item.card.assessment_type : undefined
    ) || (item.card?.card_type === 'values_auction_result' ? 'values_auction' : undefined)

    return (
      <AssessmentCardRenderer
        card={item.card}
        assessmentType={cardAssessmentType}
        onStart={() => {}}
        onAnswer={() => {}}
        onContinue={() => {}}
        onContinueChat={() => {}}
        onAddLabels={onAddLabels}
      />
    )
  }

  if (item.kind === 'assessment_suggest') {
    // 测评引导卡片
    const card = item.card
    return (
      <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 animate-fade-in-up">
        <div className="flex items-start gap-3">
          <Brain className="h-5 w-5 text-primary mt-0.5" />
          <div className="flex-1">
            <h3 className="font-medium text-sm">{card?.title || '性格测试'}</h3>
            <p className="text-xs text-muted-foreground mt-1">{card?.description || '了解你的性格类型'}</p>
            <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <span>⏱</span>
                <span>{card?.duration || '约5分钟'}</span>
              </span>
              <span className="flex items-center gap-1">
                <span>🎁</span>
                <span>{card?.reward || '匹配更精准'}</span>
              </span>
            </div>
            <button
              onClick={() => {
                const assessmentType = card?.assessment_type || 'mbti_16'
                const typeMap: Record<string, 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love'> = {
                  mbti_16: 'mbti_16',
                  attachment_style: 'attachment_style',
                  big_five: 'big_five',
                }
                onOpenAssessment?.(typeMap[assessmentType] || 'mbti_16')
              }}
              className="mt-3 rounded-full bg-primary px-4 py-1.5 text-xs text-primary-foreground"
            >
              {card?.action_label || '开始测评'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (item.kind === 'suggested_actions') {
    return (
      <div className="flex flex-wrap gap-2">
        {item.actions.map((action) => (
          <button
            key={action.action_id}
            onClick={() => {
              if (action.semantic_payload?.kind === 'start_assessment') {
                const assessmentType = action.semantic_payload?.assessment_type || 'mbti'
                const typeMap: Record<string, 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love'> = {
                  mbti: 'mbti_16',
                  attachment: 'attachment_style',
                  big_five: 'big_five',
                  sternberg: 'sternberg_triangular_love',
                }
                onOpenAssessment?.(typeMap[assessmentType] || 'mbti_16')
                return
              }
              onSubmitAction?.(action.action_id)
            }}
            disabled={isSubmittingTurn}
            className="rounded-full border border-border bg-secondary px-3 py-1.5 text-xs text-foreground disabled:opacity-60"
          >
            {action.label}
          </button>
        ))}
      </div>
    )
  }

  if (item.kind === 'message') {
    const isUser = item.type === 'user'
    // 检测是否为"发送中"状态的临时消息
    const isSending = item.content === '🎤 语音消息识别中...'

    return (
      <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
        <div className={cn('max-w-[80%]', isUser ? 'order-1' : '')}>
          <div
            className={cn(
              'rounded-2xl text-sm leading-relaxed whitespace-pre-line',
              isUser
                ? isSending
                  ? 'bg-muted text-muted-foreground rounded-br-md px-3.5 py-2.5 animate-pulse'  // 发送中：灰色 + 脉冲动画
                  : 'bg-primary text-primary-foreground rounded-br-md px-3.5 py-2.5'  // 正常：蓝色
                : 'bg-card border border-border rounded-bl-md px-4 py-3',
            )}
          >
            {isUser ? (
              <div className="space-y-2">
                {item.mediaType === 'image' && item.mediaUrl ? (
                  <div className="relative h-28 w-28 overflow-hidden rounded-2xl bg-black/5">
                    <Image
                      src={item.mediaUrl}
                      alt="用户发送的图片"
                      fill
                      className="object-cover"
                      unoptimized
                    />
                  </div>
                ) : null}
                <div className="flex items-center gap-2">
                  {isSending && (
                    <div className="w-3 h-3 border-2 border-muted-foreground/30 border-t-muted-foreground rounded-full animate-spin" />
                  )}
                  <span>{item.content}</span>
                </div>
              </div>
            ) : (
              <XiaoyaRichText
                content={item.content}
                mediaType={item.mediaType}
                mediaUrl={item.mediaUrl}
                mediaMetadata={item.mediaMetadata}
                autoPlayAudio={item.isNewMessage}  // 发现页新消息自动播放（类似豆包）
                className="space-y-3.5"
              />
            )}
          </div>
          <p className={cn('text-[10px] text-muted-foreground mt-1', isUser ? 'text-right' : '')}>
            {item.timestamp}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-2 max-w-[92%]">
      {item.title ? <p className="text-xs text-muted-foreground">{item.title}</p> : null}
      <div className="space-y-3">
        {item.candidates.map((candidate, index) => (
          <DiscoveryCandidateCard
            key={`${item.id}-${candidate.id}`}
            candidate={candidate}
            sessionId={sessionId}
            onViewCandidate={onViewCandidate}
            className="animate-fade-in-up"
            style={{ animationDelay: `${index * 80}ms` }}
          />
        ))}
      </div>
    </div>
  )
}

export default function DiscoverPage({
  onViewCandidate,
  onSessionIdChange,
}: DiscoverPageProps) {
  const VOICE_CANCEL_THRESHOLD_PX = 72
  const [hasHydrated, setHasHydrated] = useState(false)
  const {
    timelineItems,
    inputValue,
    setInputValue,
    isTyping,
    currentPrefs,
    composerPlaceholder,
    composerDisabled,
    isSubmittingTurn,
    loadError,
    usingMockData,
    isLoadingSession,
    chatEndRef,
    submitTurn,
    sessionId,
    reloadSession,
    createNewSession,
    switchSession,
    removeSuggestedActions,
    addTimelineItem,  // 新增：用于添加临时消息
    removeTimelineItem,  // 新增：用于移除临时消息
  } = useDiscoverySession(onSessionIdChange)

  useEffect(() => {
    setHasHydrated(true)
  }, [])

  // 用户打开发现页，立即标记推荐卡片为已读。
  // 被动推荐是否显示在发现页，应该由 discovery_pushed 决定，
  // 不能在页面刚打开时抢先把 case 标成 viewed，否则会和补推逻辑打架。
  useEffect(() => {
    if (!getAccessToken()) return
    const profileId = getProfileId()
    if (!profileId || typeof profileId !== 'number') return

    async function markAllUnreadAsRead() {
      try {
        // 1. 标记所有推荐卡片为已读
        const response = await fetchRecommendationCards(profileId as number)
        const cards = response.cards || []
        const cardIds = cards.filter((card) => card.card_id).map((card) => card.card_id!)

        if (cardIds.length > 0) {
          await markRecommendationCardsRead(profileId as number, cardIds)
          console.log('[发现页已读] 标记了', cardIds.length, '张推荐卡片为已读')
        }

      } catch (error) {
        if (isAuthRequiredGatewayError(error)) {
          const sessionStillValid = await confirmSessionOrRedirectToWelcome()
          if (sessionStillValid) {
            console.warn('[发现页已读] 后台标记已读鉴权失败，跳过本次同步', error)
          }
          return
        }
        console.error('[发现页标记已读失败]:', error)
      }
    }

    markAllUnreadAsRead()
  }, []) // 组件加载时执行一次

  // 新增：会话列表显示状态
  const [showSessionList, setShowSessionList] = useState(false)
  const [isVoiceCanceling, setIsVoiceCanceling] = useState(false)
  const isVoiceCancelingRef = useRef(false)
  const voiceGestureRef = useRef<{
    pointerId: number | null
    startY: number
  }>({ pointerId: null, startY: 0 })

  // Voice input functionality - 按住说话、松开自动发送
  // 临时消息ID，用于在语音识别过程中显示"发送中"状态
  const [voiceTempMessageId, setVoiceTempMessageId] = useState<string | null>(null)

  const {
    isRecording,
    isProcessing,
    startRecording,
    stopRecording,
    cancelRecording,
    recordingDuration,
  } = useVoiceInput({
    onTranscript: (text) => {
      // 语音识别完成后，自动发送消息（不再添加到输入框）
      if (text.trim()) {
        // 【乐观更新】先移除"识别中"临时消息，再通过 submitTurn 显示真实消息
        if (voiceTempMessageId) {
          removeTimelineItem(voiceTempMessageId)
        }
        setVoiceTempMessageId(null)
        void submitTurn({ user_message: text.trim() })
      } else {
        // 识别失败，移除临时消息
        if (voiceTempMessageId) {
          removeTimelineItem(voiceTempMessageId)
        }
        setVoiceTempMessageId(null)
        toast.error('未识别到语音内容')
      }
    },
    onError: (error) => {
      // 识别错误，移除临时消息
      if (voiceTempMessageId) {
        removeTimelineItem(voiceTempMessageId)
      }
      setVoiceTempMessageId(null)
      toast.error(error)
    },
    maxDurationMs: 60000,
  })

  const formatRecordingTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  useEffect(() => {
    isVoiceCancelingRef.current = isVoiceCanceling
  }, [isVoiceCanceling])

  useEffect(() => {
    if (!isRecording) {
      setIsVoiceCanceling(false)
      isVoiceCancelingRef.current = false
      voiceGestureRef.current = { pointerId: null, startY: 0 }
    }
  }, [isRecording])

  const prefChips = currentPrefs.length
    ? currentPrefs
    : usingMockData
      ? ['同城优先', '本科以上']
      : []
  const showSessionLoading = !hasHydrated || isLoadingSession
  const newSessionButtonDisabled = hasHydrated ? showSessionLoading : undefined
  const [showActionMenu, setShowActionMenu] = useState(false)
  const [showPhotoModes, setShowPhotoModes] = useState(false)
  const [showAssessmentSubmenu, setShowAssessmentSubmenu] = useState(false)
  const [photoSearchMode, setPhotoSearchMode] = useState<DiscoveryPhotoSearchMode>('face')
  const [photoSearchCaption, setPhotoSearchCaption] = useState('')
  const [photoAttachmentSource, setPhotoAttachmentSource] = useState('')
  const [photoAttachmentPreview, setPhotoAttachmentPreview] = useState('')
  const [isPhotoSearchSending, setIsPhotoSearchSending] = useState(false)
  const [isPhotoDragActive, setIsPhotoDragActive] = useState(false)
  const [assessmentCard, setAssessmentCard] = useState<AssessmentCard | null>(null)
  const [assessmentId, setAssessmentId] = useState<string | null>(null)
  const [currentAssessmentType, setCurrentAssessmentType] = useState<'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love'>('mbti_16')
  const [assessmentQuestionHistory, setAssessmentQuestionHistory] = useState<AssessmentQuestionCard['question_data'][]>([])
  const [assessmentBusy, setAssessmentBusy] = useState(false)
  const [valuesAuctionCard, setValuesAuctionCard] = useState<ValuesAuctionCard | null>(null)
  const [valuesAuctionBusy, setValuesAuctionBusy] = useState(false)
  const userKey = String(getProfileId() || getUserId() || '')
  const currentProfileId = typeof getProfileId() === 'number' ? (getProfileId() as number) : null
  const photoFileInputRef = useRef<HTMLInputElement | null>(null)

  const clearPhotoComposer = () => {
    setPhotoAttachmentSource('')
    setPhotoAttachmentPreview('')
    setPhotoSearchCaption('')
    setIsPhotoSearchSending(false)
    setShowPhotoModes(false)
    setPhotoSearchMode('face')
  }

  const photoModeLabel =
    photoSearchMode === 'face'
      ? '找像这张脸'
      : photoSearchMode === 'style'
        ? '找这种感觉'
        : '像某明星'

  const photoComposerPlaceholder =
    photoSearchMode === 'face'
      ? '再补一句，比如 笑起来像这张'
      : photoSearchMode === 'style'
        ? '再补一句，比如 清爽、自然、温柔'
        : '输入明星名字，比如 刘亦菲'

  const photoReadyToSend =
    photoSearchMode === 'celebrity'
      ? Boolean(photoSearchCaption.trim())
      : Boolean(photoAttachmentSource.trim())

  const openAssessmentCard = async (
    assessmentType: 'mbti_16' | 'attachment_style' | 'big_five' | 'sternberg_triangular_love' = 'mbti_16'
  ) => {
    if (!userKey || assessmentBusy) return
    setAssessmentBusy(true)
    setCurrentAssessmentType(assessmentType)
    setValuesAuctionCard(null)
    removeSuggestedActions()
    try {
      const intro = await startAssessment(userKey, assessmentType)
      setAssessmentId(intro.assessment_id)
      setAssessmentCard(intro)
      setAssessmentQuestionHistory([])
      // 打开测评卡片后，滚动到底部
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 150)
    } catch (error) {
      const assessmentNames = {
        'mbti_16': 'MBTI',
        'attachment_style': '相处模式',
        'big_five': '大五人格',
        'sternberg_triangular_love': '爱情三元论',
      }
      notifyError(error, `打开 ${assessmentNames[assessmentType]} 测评失败`)
    } finally {
      setAssessmentBusy(false)
    }
  }

  const clearAssessmentCard = () => {
    setAssessmentCard(null)
    setAssessmentId(null)
    setAssessmentQuestionHistory([])
    setCurrentAssessmentType('mbti_16')
    // 滚动到底部显示小雅消息
    setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 150)
  }

  const openValuesAuctionCard = async () => {
    if (!userKey || valuesAuctionBusy) return
    setValuesAuctionBusy(true)
    setAssessmentCard(null)
    removeSuggestedActions()
    try {
      const intro = await startValuesAuction(userKey)
      setValuesAuctionCard(intro)
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 150)
    } catch (error) {
      notifyError(error, '打开价值观拍卖会失败')
    } finally {
      setValuesAuctionBusy(false)
    }
  }

  const clearValuesAuctionCard = () => {
    setValuesAuctionCard(null)
    setTimeout(() => {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 150)
  }

  const handleAddLabels = async (selectedLabels: string[]) => {
    if (!userKey) return
    try {
      await addAssessmentLabels(userKey, selectedLabels)
      toast.success(`已添加 ${selectedLabels.length} 个标签到个人主页`)
    } catch (error) {
      notifyError(error, '添加标签失败')
    }
  }

  const processPhotoFile = async (file: File) => {
    try {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        throw new Error('目前只支持 JPG、PNG、WEBP')
      }
      if (file.size > 10 * 1024 * 1024) {
        throw new Error('图片不能超过 10MB')
      }
      const compressed = await compressPhotoSearchImage(file)
      setPhotoAttachmentSource(compressed)
      setPhotoAttachmentPreview(compressed)
      setPhotoSearchMode((prev) => (prev === 'celebrity' ? 'face' : prev))
      setShowPhotoModes(true)
    } catch (error) {
      notifyError(error, '图片处理失败')
    }
  }

  const handlePhotoFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      await processPhotoFile(file)
    } finally {
      if (photoFileInputRef.current) {
        photoFileInputRef.current.value = ''
      }
    }
  }

  const submitPhotoSearch = async () => {
    if (!currentProfileId || !photoReadyToSend || isPhotoSearchSending) return
    const userBubbleId = `photo-search-user-${Date.now()}`
    const progressId = `photo-search-progress-${Date.now()}`
    const resultId = `photo-search-result-${Date.now()}`
    const normalizedCaption = photoSearchCaption.trim()
    setIsPhotoSearchSending(true)
    addTimelineItem({
      kind: 'message',
      id: userBubbleId,
      type: 'user',
      content:
        photoSearchMode === 'celebrity'
          ? `想找像 ${normalizedCaption} 的人`
          : normalizedCaption || photoModeLabel,
      timestamp: '刚刚',
      mediaType: photoSearchMode === 'celebrity' ? undefined : 'image',
      mediaUrl: photoAttachmentPreview || photoAttachmentSource || undefined,
      isNewMessage: true,
    })
    addTimelineItem({
      kind: 'message',
      id: progressId,
      type: 'matchmaker',
      content:
        photoSearchMode === 'face'
          ? '收到这张图了，我先按脸型和五官去帮你找相似的人。'
          : photoSearchMode === 'style'
            ? '收到这张图了，我先按整体感觉和氛围去帮你找。'
            : `收到啦，我先按 ${normalizedCaption} 这个方向帮你找。`,
      timestamp: '刚刚',
    })
    try {
      const response = await searchDiscoveryByPhoto({
        profileId: currentProfileId,
        sessionId: sessionId || undefined,
        mode: photoSearchMode,
        imageSource: photoSearchMode === 'celebrity' ? undefined : photoAttachmentSource,
        queryText: normalizedCaption || undefined,
        celebrityName: photoSearchMode === 'celebrity' ? normalizedCaption : undefined,
        topK: 12,
      })
      removeTimelineItem(progressId)
      if (response.session_sync?.success && sessionId) {
        await reloadSession()
      } else {
        addTimelineItem({
          kind: 'message',
          id: `${resultId}-summary`,
          type: 'matchmaker',
          content:
            response.result_count && response.result_count > 0
              ? `先帮你捞到了 ${response.result_count} 个方向比较贴近的人，你往下看。`
              : '这次我还没找到特别贴的，你可以换张图，或者补一句更明确的描述。',
          timestamp: '刚刚',
        })
        if ((response.results || []).length > 0) {
          addTimelineItem({
            kind: 'result_group',
            id: resultId,
            title:
              photoSearchMode === 'face'
                ? '按这张脸找'
                : photoSearchMode === 'style'
                  ? '按这种感觉找'
                  : `按 ${normalizedCaption} 找`,
            candidates: response.results || [],
          })
        }
      }
      clearPhotoComposer()
    } catch (error) {
      removeTimelineItem(progressId)
      addTimelineItem({
        kind: 'message',
        id: `${progressId}-error`,
        type: 'matchmaker',
        content: '这张图我刚才没处理成功，你重新发一次，我继续帮你找。',
        timestamp: '刚刚',
      })
      notifyError(error, '照片搜索失败')
    } finally {
      setIsPhotoSearchSending(false)
    }
  }

  const pageShellClass =
    'flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-background pb-14'

  // 当测评卡片出现时，自动滚动到底部
  useEffect(() => {
    if (assessmentCard || valuesAuctionCard) {
      // 使用 setTimeout 确保 DOM 更新后再滚动
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [assessmentCard, valuesAuctionCard])

  if (loadError && !canUseMockFallback()) {
    return (
      <div className={pageShellClass}>
        <ErrorState
          message={loadError}
          onRetry={() => window.location.reload()}
        />
      </div>
    )
  }

  return (
    <div className={pageShellClass}>
      {usingMockData && <DemoDataBanner />}
      <header className="flex-shrink-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="relative">
                <XiaoyaAvatar size={40} />
                <OnlineIndicator className="absolute -bottom-0.5 -right-0.5" size="sm" />
              </div>
              <div>
                <h1 className="font-medium text-foreground">小雅</h1>
                <p className="text-xs text-muted-foreground">你的专属红娘</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* 新增：历史记录按钮 */}
              <button
                onClick={() => setShowSessionList(true)}
                className="flex items-center gap-1 px-2 py-1.5 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors focus-ring"
                aria-label="查看会话历史"
              >
                <History className="w-4 h-4 text-muted-foreground" />
              </button>
              {/* 新增：新建会话按钮 */}
              <button
                onClick={() => {
                  if (!hasHydrated || isLoadingSession) return
                  void createNewSession()
                }}
                disabled={newSessionButtonDisabled}
                className="flex items-center gap-1 px-2 py-1.5 bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors focus-ring disabled:opacity-50"
                aria-label="新建会话"
              >
                <Plus className="w-4 h-4" />
                <span className="text-xs font-medium">新对话</span>
              </button>
              </div>
          </div>
        </div>
      </header>

      {/* Preference chips with scroll fade */}
      <div className="relative flex-shrink-0 px-4 py-2 border-b border-border">
        <p className="text-[10px] text-muted-foreground mb-1.5">当前条件</p>
        <div className="flex gap-2 overflow-x-auto scrollbar-hide scroll-fade-right" role="list" aria-label="已收集偏好">
          {currentPrefs.length === 0 && !usingMockData ? (
            <span className="shrink-0 px-2.5 py-1 bg-secondary text-muted-foreground text-xs rounded-md">
              {EMPTY_PREFS_PLACEHOLDER}
            </span>
          ) : (
            prefChips.map((pref, i) => (
            <span 
              key={i} 
              className="shrink-0 px-2.5 py-1 bg-secondary text-muted-foreground text-xs rounded-md animate-fade-in-up"
              style={{ animationDelay: `${i * 50}ms` }}
              role="listitem"
            >
              {pref}
            </span>
          )))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
        <div className="px-4 py-4 space-y-4">
          {showSessionLoading ? (
            <DiscoverPageSkeleton />
          ) : (
            timelineItems.map((item) => (
              <DiscoveryTimelineEntry
                key={item.id}
                item={item}
                sessionId={sessionId}
                onViewCandidate={onViewCandidate}
                onProfileUpdateResolved={() => {
                  void reloadSession()
                }}
                onAddLabels={handleAddLabels}
                onSubmitAction={(actionId) => {
                  void submitTurn({ action_id: actionId })
                }}
                onOpenAssessment={(assessmentType) => {
                  void openAssessmentCard(assessmentType)
                }}
                isSubmittingTurn={isSubmittingTurn}
              />
            ))
          )}

          {(() => {
            if (showSessionLoading) return null
            // 判断是否应该显示 assessmentCard state中的卡片
            // 如果timeline中已经有相同assessment_id的结果卡片，就不要重复显示
            if (!assessmentCard || !assessmentId) return null

            // 如果不是结果卡片，总是显示（intro, question, feedback等）
            if (assessmentCard.card_type !== 'assessment_result') {
              return (
                <div className="flex justify-start">
                  <div className="w-full max-w-[92%]">
                    <AssessmentCardRenderer
                      card={assessmentCard}
                      onStart={async () => {
                        const next = await beginAssessment(assessmentId)
                        setAssessmentCard(next)
                      }}
                      onAnswer={async (answer) => {
                        if (assessmentCard.card_type !== 'assessment_question') return
                        setAssessmentQuestionHistory((prev) => [...prev, assessmentCard.question_data])
                        const next = await answerAssessment({
                          assessmentId,
                          questionIndex: assessmentCard.question_data.current_question - 1,
                          answer,
                          userKey,
                        })
                        setAssessmentCard(next)

                        // 如果测评完成（显示结果卡片），将结果和小雅消息添加到对话流
                        // 但不清空state，让用户能看到结果卡片
                        // 用户点击"继续和小雅聊天"按钮时才清空state
                        if (next.card_type === 'assessment_result' && userKey) {
                          try {
                            const xiaoyaResult = await getXiaoyaMessage(userKey, currentAssessmentType)
                            if (xiaoyaResult.has_message && xiaoyaResult.message) {
                              if (sessionId) {
                                try {
                                  await waitForPsychologyXiaoyaResult()
                                  await addXiaoyaMessageToDiscovery({
                                    userKey,
                                    sessionId,
                                    message: xiaoyaResult.message,
                                    resultData: next.result_data,
                                    assessmentType: currentAssessmentType,
                                  })
                                  await reloadSession()
                                  // ✅ 不立即清空state，让用户能看到结果卡片
                                  // clearAssessmentCard() 移到 onContinueChat 回调中
                                } catch (discoveryError) {
                                  console.warn('[onAnswer] 添加到discovery失败，可能是session不存在:', discoveryError)
                                  // 失败不影响当前结果展示，只是消息不会融入对话流
                                }
                              } else {
                                console.warn('[onAnswer] sessionId为空，跳过添加到discovery session')
                              }
                            }
                          } catch (error) {
                            console.error('[onAnswer] 获取小雅消息失败:', error)
                          }
                        }
                      }}
                      onContinue={async () => {
                        if (assessmentCard.card_type !== 'assessment_feedback') return
                        setAssessmentCard({
                          card_type: 'assessment_question',
                          assessment_id: assessmentId,
                          question_data: assessmentCard.next_question,
                        })
                      }}
                      onContinueChat={() => {
                        // 用户点击"继续和小雅聊天"，清除测评卡片state
                        // 小雅消息已经在测评完成时添加到对话流，不需要再次添加
                        clearAssessmentCard()

                        // 滚动到底部
                        setTimeout(() => {
                          chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
                        }, 150)
                      }}
                      onPrevious={
                        assessmentQuestionHistory.length > 0
                          ? () => {
                              const previous = assessmentQuestionHistory[assessmentQuestionHistory.length - 1]
                              setAssessmentQuestionHistory((prev) => prev.slice(0, -1))
                              setAssessmentCard({
                                card_type: 'assessment_question',
                                assessment_id: assessmentId,
                                question_data: previous,
                              })
                            }
                          : undefined
                      }
                      onAddLabels={handleAddLabels}
                      assessmentType={currentAssessmentType}
                    />
                  </div>
                </div>
              )
            }

            // 如果是结果卡片，检查timeline中是否已经有相同的结果
            const existingResultInTimeline = timelineItems.some(item =>
              item.kind === 'assessment_result' &&
              item.card?.assessment_id === assessmentId
            )

            // 如果timeline中已经有，就不重复显示state中的
            if (existingResultInTimeline) return null

            // 否则显示结果卡片
            return (
              <div className="flex justify-start">
                <div className="w-full max-w-[92%]">
                  <AssessmentCardRenderer
                    card={assessmentCard}
                    onStart={async () => {
                      const next = await beginAssessment(assessmentId)
                      setAssessmentCard(next)
                    }}
                    onAnswer={() => {}}
                    onContinue={() => {}}
                    onContinueChat={() => {
                      // 用户点击"继续和小雅聊天"，清除测评卡片state
                      // 小雅消息已经在测评完成时添加到对话流，不需要再次添加
                      clearAssessmentCard()

                      // 滚动到底部
                      setTimeout(() => {
                        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
                      }, 150)
                    }}
                    onPrevious={
                      assessmentQuestionHistory.length > 0
                        ? () => {
                            const previous = assessmentQuestionHistory[assessmentQuestionHistory.length - 1]
                            setAssessmentQuestionHistory((prev) => prev.slice(0, -1))
                            setAssessmentCard({
                              card_type: 'assessment_question',
                              assessment_id: assessmentId,
                              question_data: previous,
                            })
                          }
                        : undefined
                    }
                    onAddLabels={handleAddLabels}
                    assessmentType={currentAssessmentType}
                  />
                </div>
              </div>
            )
          })()}

          {(() => {
            if (showSessionLoading) return null
            if (!valuesAuctionCard) return null

            const shouldHideStateResult =
              valuesAuctionCard.card_type === 'values_auction_result' &&
              timelineItems.some(
                (item) =>
                  item.kind === 'assessment_result' &&
                  item.card?.card_type === 'values_auction_result' &&
                  item.card?.assessment_id === valuesAuctionCard.assessment_id,
              )

            if (shouldHideStateResult) return null

            return (
              <div className="flex justify-start">
                <div className="w-full max-w-[92%]">
                  <ValuesAuctionCardRenderer
                    card={valuesAuctionCard}
                    userKey={userKey}
                    onStart={async () => {
                      if (!('assessment_id' in valuesAuctionCard)) return
                      const next = await getValuesAuctionLots(valuesAuctionCard.assessment_id)
                      setValuesAuctionCard(next)
                    }}
                    onSubmitBids={async (bids) => {
                      if (!('assessment_id' in valuesAuctionCard)) return
                      const next = await submitValuesAuctionBids({
                        assessmentId: valuesAuctionCard.assessment_id,
                        userKey,
                        bids,
                      })
                      setValuesAuctionCard(next)

                      // 如果结果卡片包含小雅消息，自动添加到对话流
                      // 这样小雅的回复会显示在结果卡片下方
                      if (next.xiaoya_message && sessionId) {
                        try {
                          await waitForPsychologyXiaoyaResult()
                          await addXiaoyaMessageToDiscovery({
                            userKey,
                            sessionId,
                            message: next.xiaoya_message,
                            resultData: next,  // 传递整个结果卡片，包含 card_type
                            assessmentType: 'values_auction',  // 新增：指定测评类型
                          })
                          await reloadSession()
                        } catch (discoveryError) {
                          console.warn('[onSubmitBids] 添加到discovery失败:', discoveryError)
                          // 失败不影响结果展示
                        }
                      }
                    }}
                    onViewInterpretation={async () => {
                      if (!('assessment_id' in valuesAuctionCard)) return
                      const next = await getValuesAuctionInterpretation({
                        assessmentId: valuesAuctionCard.assessment_id,
                        userKey,
                      })
                      setValuesAuctionCard(next)
                    }}
                    onContinue={clearValuesAuctionCard}
                  />
                </div>
              </div>
            )
          })()}

          {!showSessionLoading && isTyping ? <TypingIndicator name="小雅" /> : null}

          {/* Recording indicator - 微信式录音提示 */}
          {isRecording && (
            <div className="flex justify-end animate-fade-in-up">
              <div className="max-w-[80%]">
                <div
                  className={cn(
                    'rounded-2xl border rounded-br-md px-4 py-3 transition-all',
                    isVoiceCanceling
                      ? 'bg-destructive/15 border-destructive/30'
                      : 'bg-primary/20 border-primary/30',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <div
                      className={cn(
                        'w-2 h-2 rounded-full animate-pulse',
                        isVoiceCanceling ? 'bg-destructive' : 'bg-rose',
                      )}
                    />
                    <span className={cn('text-sm font-medium', isVoiceCanceling ? 'text-destructive' : 'text-primary')}>
                      {isVoiceCanceling ? '松开取消' : formatRecordingTime(recordingDuration)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {isVoiceCanceling ? '松开后将取消这条语音' : '松开发送 · 上滑取消'}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Input pinned below scrollable messages; app shell bottom nav is outside this column */}
      <div className="flex-shrink-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        {showActionMenu && (
          <div
            className="mb-2 rounded-2xl bg-background animate-fade-in-up"
            onClick={(e) => {
              if (e.target === e.currentTarget) {
                setShowActionMenu(false)
                setShowAssessmentSubmenu(false)
              }
            }}
          >
            <div className="rounded-2xl border border-border bg-card p-3">
              {/* 心理测评折叠按钮 */}
              <button
                onClick={() => setShowAssessmentSubmenu(!showAssessmentSubmenu)}
                className="flex items-center justify-between w-full p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-expanded={showAssessmentSubmenu}
                aria-label="心理测评"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <ClipboardList className="w-5 h-5 text-primary" />
                  </div>
                  <span className="text-sm font-medium text-foreground">心理测评</span>
                </div>
                <ChevronDown 
                  className={cn(
                    "w-5 h-5 text-muted-foreground transition-transform duration-200",
                    showAssessmentSubmenu && "rotate-180"
                  )} 
                />
              </button>

              {/* 测评子菜单 */}
              {showAssessmentSubmenu && (
                <div className="mt-2 grid grid-cols-2 gap-3 animate-fade-in-up">
                  {/* MBTI测评 */}
                  <button
                    onClick={() => {
                      void openAssessmentCard('mbti_16')
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="MBTI测评"
                  >
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <Brain className="w-5 h-5 text-primary" />
                    </div>
                    <span className="text-xs text-foreground">MBTI</span>
                  </button>

                  {/* 相处模式测评 */}
                  <button
                    onClick={() => {
                      void openAssessmentCard('attachment_style')
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="相处模式测评"
                  >
                    <div className="w-10 h-10 rounded-full bg-coral/10 flex items-center justify-center">
                      <Heart className="w-5 h-5 text-coral" />
                    </div>
                    <span className="text-xs text-foreground">相处模式</span>
                  </button>

                  <button
                    onClick={() => {
                      void openAssessmentCard('big_five')
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="大五人格测评"
                  >
                    <div className="w-10 h-10 rounded-full bg-sage/10 flex items-center justify-center">
                      <Sparkles className="w-5 h-5 text-sage" />
                    </div>
                    <span className="text-xs text-foreground">大五人格</span>
                  </button>

                  <button
                    onClick={() => {
                      void openAssessmentCard('sternberg_triangular_love')
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="爱情三元论测评"
                  >
                    <div className="w-10 h-10 rounded-full bg-amber/10 flex items-center justify-center">
                      <Heart className="w-5 h-5 text-amber" />
                    </div>
                    <span className="text-xs text-foreground">爱情三元论</span>
                  </button>

                  {/* 价值观拍卖会 */}
                  <button
                    onClick={() => {
                      void openValuesAuctionCard()
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="价值观拍卖会"
                  >
                    <div className="w-10 h-10 rounded-full bg-amber/10 flex items-center justify-center">
                      <Coins className="w-5 h-5 text-amber" />
                    </div>
                    <span className="text-xs text-foreground">价值观拍卖</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        <input
          ref={photoFileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/*"
          className="hidden"
          onChange={handlePhotoFileChange}
        />

        {(showPhotoModes || photoAttachmentSource || photoSearchMode === 'celebrity') && (
          <div className="mb-2 space-y-2">
            <div className="flex items-center gap-2 overflow-x-auto pb-1">
              {[
                { key: 'face' as const, label: '找像这张脸', icon: UserRoundSearch },
                { key: 'style' as const, label: '找这种感觉', icon: Sparkles },
                { key: 'celebrity' as const, label: '像某明星', icon: Star },
              ].map((item) => {
                const Icon = item.icon
                const active = photoSearchMode === item.key
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => {
                      setPhotoSearchMode(item.key)
                      setShowPhotoModes(true)
                    }}
                    className={cn(
                      'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors',
                      active
                        ? 'border-primary/40 bg-primary/10 text-primary'
                        : 'border-border bg-card text-muted-foreground',
                    )}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {item.label}
                  </button>
                )
              })}
            </div>

            {(photoAttachmentSource || photoSearchMode === 'celebrity') && (
              <div className="rounded-2xl border border-border bg-card px-3 py-2">
                {photoAttachmentSource ? (
                  <div className="flex items-start gap-3">
                    <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-xl border border-border bg-secondary">
                      <Image
                        src={photoAttachmentPreview || photoAttachmentSource}
                        alt="已选图片"
                        fill
                        className="object-cover"
                        unoptimized
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">{photoModeLabel}</p>
                      <p className="mt-1 text-xs text-muted-foreground">图片已经挂进对话框了，可以直接发送，也可以补一句话。</p>
                    </div>
                    <button
                      type="button"
                      onClick={clearPhotoComposer}
                      className="rounded-full p-1 text-muted-foreground hover:bg-secondary"
                      aria-label="移除图片"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">{photoModeLabel}</p>
                      <p className="mt-1 text-xs text-muted-foreground">直接输入明星名字，再点发送就行。</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setShowPhotoModes(false)
                        setPhotoSearchMode('face')
                        setPhotoSearchCaption('')
                      }}
                      className="rounded-full p-1 text-muted-foreground hover:bg-secondary"
                      aria-label="收起图片搜索模式"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 微信式设计：不显示"识别中..."等待状态，让用户感觉已即时发送 */}
        {/* isProcessing 状态下不显示任何UI提示，后台静默处理 */}

        <div
          className={cn(
            'flex items-center gap-2 rounded-xl px-3 py-2 transition-all focus-within:ring-2 focus-within:ring-primary/30',
            isPhotoDragActive ? 'bg-primary/10 ring-2 ring-primary/30' : 'bg-secondary',
          )}
          onDragOver={(event) => {
            event.preventDefault()
            if (photoSearchMode === 'celebrity') {
              setPhotoSearchMode('face')
            }
            setIsPhotoDragActive(true)
            setShowPhotoModes(true)
          }}
          onDragLeave={(event) => {
            event.preventDefault()
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setIsPhotoDragActive(false)
            }
          }}
          onDrop={(event) => {
            event.preventDefault()
            setIsPhotoDragActive(false)
            const file = Array.from(event.dataTransfer.files || []).find((item) => item.type.startsWith('image/'))
            if (!file) return
            void processPhotoFile(file)
          }}
        >
          <button
            aria-label={showActionMenu ? '收起菜单' : '展开菜单'}
            onClick={() => setShowActionMenu((prev) => !prev)}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              showActionMenu ? 'bg-primary text-primary-foreground rotate-45' : 'bg-muted hover:bg-primary/10 text-muted-foreground',
            )}
          >
            <Plus className="w-5 h-5" />
          </button>
          <input
            value={photoAttachmentSource || photoSearchMode === 'celebrity' ? photoSearchCaption : inputValue}
            onChange={(e) => {
              if (photoAttachmentSource || photoSearchMode === 'celebrity') {
                setPhotoSearchCaption(e.target.value)
                return
              }
              setInputValue(e.target.value)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && (inputValue.trim() || photoReadyToSend)) {
                e.preventDefault()
                if (photoReadyToSend) {
                  void submitPhotoSearch()
                } else {
                  void submitTurn({ user_message: inputValue.trim() })
                }
              }
            }}
            onPaste={(event) => {
              const imageItem = Array.from(event.clipboardData.items || []).find((item) => item.type.startsWith('image/'))
              if (!imageItem) return
              const file = imageItem.getAsFile()
              if (!file) return
              event.preventDefault()
              if (photoSearchMode === 'celebrity') {
                setPhotoSearchMode('face')
              }
              setShowPhotoModes(true)
              void processPhotoFile(file)
            }}
            placeholder={
              isRecording
                ? '请说话...'
                : photoAttachmentSource || photoSearchMode === 'celebrity'
                  ? photoComposerPlaceholder
                  : composerPlaceholder
            }
            disabled={composerDisabled || isSubmittingTurn || isRecording || isPhotoSearchSending}
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-60"
            aria-label="输入消息"
          />

          <button
            type="button"
            aria-label="选择图片"
            onClick={() => {
              setShowPhotoModes(true)
              if (photoSearchMode === 'celebrity') return
              photoFileInputRef.current?.click()
            }}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              photoAttachmentSource || photoSearchMode === 'celebrity'
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80',
            )}
          >
            <ImagePlus className="w-5 h-5" />
          </button>
          
          {/* Voice input button - 按住说话、松开自动发送 */}
          <button
            aria-label="按住说话"
            onPointerDown={(e) => {
              e.preventDefault()
              e.currentTarget.setPointerCapture(e.pointerId)
              voiceGestureRef.current = {
                pointerId: e.pointerId,
                startY: e.clientY,
              }
              setIsVoiceCanceling(false)
              isVoiceCancelingRef.current = false
              if (!isRecording && !composerDisabled && !isSubmittingTurn && !isProcessing && !isPhotoSearchSending) {
                void startRecording()
              }
            }}
            onPointerMove={(e) => {
              if (voiceGestureRef.current.pointerId !== e.pointerId || !isRecording) return
              const deltaY = voiceGestureRef.current.startY - e.clientY
              const nextCanceling = deltaY >= VOICE_CANCEL_THRESHOLD_PX
              isVoiceCancelingRef.current = nextCanceling
              setIsVoiceCanceling(nextCanceling)
            }}
            onPointerUp={(e) => {
              e.preventDefault()
              if (voiceGestureRef.current.pointerId === e.pointerId) {
                e.currentTarget.releasePointerCapture(e.pointerId)
              }
              if (isRecording) {
                if (isVoiceCancelingRef.current) {
                  cancelRecording()
                } else {
                  // 【乐观更新】松开麦克风时立即显示"发送中"临时消息
                  const tempId = `voice-temp-${Date.now()}`
                  setVoiceTempMessageId(tempId)
                  addTimelineItem({
                    kind: 'message',
                    id: tempId,
                    type: 'user',
                    content: '语音消息识别中...',  // 特殊标记：发送中状态
                    timestamp: '刚刚',
                    isNewMessage: true,
                  })
                  stopRecording()
                }
              }
              setIsVoiceCanceling(false)
              isVoiceCancelingRef.current = false
              voiceGestureRef.current = { pointerId: null, startY: 0 }
            }}
            onPointerCancel={(e) => {
              if (voiceGestureRef.current.pointerId === e.pointerId) {
                e.currentTarget.releasePointerCapture(e.pointerId)
              }
              if (isRecording) {
                cancelRecording()
              }
              setIsVoiceCanceling(false)
              isVoiceCancelingRef.current = false
              voiceGestureRef.current = { pointerId: null, startY: 0 }
            }}
            disabled={composerDisabled || isSubmittingTurn || isProcessing || isPhotoSearchSending}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all touch-none select-none',
              isRecording
                ? isVoiceCanceling
                  ? 'bg-destructive text-white scale-110'
                  : 'bg-rose text-white animate-pulse scale-110'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80 active:scale-95'
            )}
          >
            <Mic className="w-5 h-5" />
          </button>
          
          <button
            aria-label="发送消息"
            onClick={() => {
              if (photoReadyToSend) {
                void submitPhotoSearch()
                return
              }
              void submitTurn({ user_message: inputValue.trim() })
            }}
            disabled={
              composerDisabled ||
              isSubmittingTurn ||
              isRecording ||
              isPhotoSearchSending ||
              (!inputValue.trim() && !photoReadyToSend)
            }
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              (inputValue.trim() || photoReadyToSend) && !isRecording
                ? 'bg-primary hover:bg-primary/90' 
                : 'bg-muted'
            )}
          >
            {isSubmittingTurn || isPhotoSearchSending ? (
              <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
            ) : (
              <Send className={cn('w-4 h-4', (inputValue.trim() || photoReadyToSend) && !isRecording ? 'text-primary-foreground' : 'text-muted-foreground')} />
            )}
          </button>
        </div>
      </div>

      {/* 新增：会话历史列表弹窗 */}
      {showSessionList && (
        <DiscoverySessionList
          currentSessionId={sessionId}
          onSelectSession={(targetSessionId) => {
            void switchSession(targetSessionId)
          }}
          onCreateNewSession={() => {
            void createNewSession()
          }}
          onClose={() => setShowSessionList(false)}
        />
      )}
    </div>
  )
}
