'use client'

import { useState, useEffect } from 'react'
import { ArrowLeft, BadgeCheck, Bookmark, ChevronRight, ChevronDown, Mail, Mic, Plus, Search, Send, X, Brain, Heart, Sparkles, ClipboardList, Coins } from 'lucide-react'
import { AssessmentCardRenderer } from '@/components/assessment/AssessmentCardRenderer'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
import Image from 'next/image'
import { EmptyRecommendations, EmptySearchResults } from './ui/empty-states'
import { InboxItemSkeleton, DiscoverPageSkeleton } from './ui/skeletons'
import { TypingIndicator } from './ui/typing-indicator'
import { OnlineIndicator } from './ui/animations'
import { DiscoveryCandidateCard } from './discovery-candidate-card'
import { DiscoveryProfileUpdatePrompt } from './discovery-profile-update-prompt'
import type { DiscoveryTimelineItem } from '@/lib/discovery/map-discovery-view'
import { cn } from '@/lib/utils'
import { getProfileId, getUserId } from '@/lib/auth/session'
import {
  markRecommendationCardsRead,
  postRecommendationAction,
} from '@/lib/api/endpoints/recommendation'
import { replyProxyIntroCase } from '@/lib/api/endpoints/proxy-intro'
import { useRecommendationInbox, type InboxItem } from '@/hooks/use-recommendation-inbox'
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

interface DiscoverPageProps {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onOpenInbox: () => void
  inboxUnreadCount?: number
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
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onProfileUpdateResolved?: () => void
  onAddLabels?: (selectedLabels: string[]) => Promise<void>
  onSubmitAction?: (actionId: string) => void
  onOpenAssessment?: (assessmentType: 'mbti_16' | 'attachment_style' | 'love_language') => void
  isSubmittingTurn?: boolean
}) {
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
    const cardAssessmentType = item.card?.assessment_type ||
      (item.card?.card_type === 'values_auction_result' ? 'values_auction' : undefined)

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

  if (item.kind === 'suggested_actions') {
    return (
      <div className="flex flex-wrap gap-2">
        {item.actions.map((action) => (
          <button
            key={action.action_id}
            onClick={() => {
              if (action.semantic_payload?.kind === 'start_assessment') {
                const assessmentType = action.semantic_payload?.assessment_type || 'mbti'
                const typeMap: Record<string, 'mbti_16' | 'attachment_style' | 'love_language'> = {
                  mbti: 'mbti_16',
                  attachment: 'attachment_style',
                  values: 'love_language',
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
    return (
      <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
        <div className={cn('max-w-[80%]', isUser ? 'order-1' : '')}>
          <div
            className={cn(
              'px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-line',
              isUser
                ? 'bg-primary text-primary-foreground rounded-br-md'
                : 'bg-card border border-border rounded-bl-md',
            )}
          >
            {isUser ? item.content : <XiaoyaRichText content={item.content} />}
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
  onOpenInbox,
  inboxUnreadCount = 0,
  onSessionIdChange,
}: DiscoverPageProps) {
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
    removeSuggestedActions,
  } = useDiscoverySession(onSessionIdChange)

  // Voice input functionality
  const {
    isRecording,
    isProcessing,
    startRecording,
    stopRecording,
    cancelRecording,
    recordingDuration,
  } = useVoiceInput({
    onTranscript: (text) => {
      setInputValue((prev) => prev + text)
    },
    onError: (error) => {
      toast.error(error)
    },
    maxDurationMs: 60000,
  })

  const handleVoiceClick = () => {
    if (isRecording) {
      stopRecording()
    } else {
      void startRecording()
    }
  }

  const formatRecordingTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const prefChips = currentPrefs.length
    ? currentPrefs
    : usingMockData
      ? ['同城优先', '本科以上']
      : []
  const [showActionMenu, setShowActionMenu] = useState(false)
  const [showAssessmentSubmenu, setShowAssessmentSubmenu] = useState(false)
  const [assessmentCard, setAssessmentCard] = useState<AssessmentCard | null>(null)
  const [assessmentId, setAssessmentId] = useState<string | null>(null)
  const [currentAssessmentType, setCurrentAssessmentType] = useState<'mbti_16' | 'attachment_style' | 'love_language'>('mbti_16')
  const [assessmentQuestionHistory, setAssessmentQuestionHistory] = useState<AssessmentQuestionCard['question_data'][]>([])
  const [assessmentBusy, setAssessmentBusy] = useState(false)
  const [valuesAuctionCard, setValuesAuctionCard] = useState<ValuesAuctionCard | null>(null)
  const [valuesAuctionBusy, setValuesAuctionBusy] = useState(false)
  const userKey = String(getProfileId() || getUserId() || '')

  const openAssessmentCard = async (assessmentType: 'mbti_16' | 'attachment_style' | 'love_language' = 'mbti_16') => {
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
        'attachment_style': '依恋风格',
        'love_language': '恋爱语言'
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

  if (isLoadingSession) {
    return (
      <div className={pageShellClass}>
        <DiscoverPageSkeleton />
      </div>
    )
  }

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
            <button 
              onClick={onOpenInbox} 
              className="relative flex items-center gap-2 px-3 py-2 bg-secondary rounded-lg hover:bg-secondary/80 transition-colors focus-ring"
              aria-label={`查看推荐来信，${inboxUnreadCount}条未读`}
            >
              <Mail className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
              <span className="text-sm">来信</span>
              {inboxUnreadCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center animate-scale-in">
                  {inboxUnreadCount}
                </span>
              )}
            </button>
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
          {timelineItems.map((item) => (
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
          ))}

          {(() => {
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
                            const xiaoyaResult = await getXiaoyaMessage(userKey)
                            if (xiaoyaResult.has_message && xiaoyaResult.message) {
                              if (sessionId) {
                                try {
                                  await addXiaoyaMessageToDiscovery({
                                    userKey,
                                    sessionId,
                                    message: xiaoyaResult.message,
                                    resultData: next.result_data,
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
                          const xiaoyaResult = await getXiaoyaMessage(userKey)
                          if (xiaoyaResult.has_message && xiaoyaResult.message) {
                            if (sessionId) {
                              try {
                                await addXiaoyaMessageToDiscovery({
                                  userKey,
                                  sessionId,
                                  message: xiaoyaResult.message,
                                  resultData: next.result_data,
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
          })()}

          {valuesAuctionCard ? (
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
          ) : null}

          {isTyping ? <TypingIndicator name="小雅" /> : null}

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

                  {/* 依恋风格测评 */}
                  <button
                    onClick={() => {
                      void openAssessmentCard('attachment_style')
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="依恋风格测评"
                  >
                    <div className="w-10 h-10 rounded-full bg-coral/10 flex items-center justify-center">
                      <Heart className="w-5 h-5 text-coral" />
                    </div>
                    <span className="text-xs text-foreground">依恋风格</span>
                  </button>

                  {/* 恋爱语言测评 */}
                  <button
                    onClick={() => {
                      void openAssessmentCard('love_language')
                      setShowActionMenu(false)
                      setShowAssessmentSubmenu(false)
                    }}
                    disabled={assessmentBusy || valuesAuctionBusy || !userKey}
                    className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary/50 hover:bg-secondary transition-all touch-target active:scale-95 disabled:opacity-60"
                    aria-label="恋爱语言测评"
                  >
                    <div className="w-10 h-10 rounded-full bg-lavender/10 flex items-center justify-center">
                      <Sparkles className="w-5 h-5 text-lavender" />
                    </div>
                    <span className="text-xs text-foreground">恋爱语言</span>
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

        {/* Recording indicator */}
        {isRecording && (
          <div className="flex items-center justify-between mb-2 px-3 py-2 bg-rose/10 rounded-lg animate-fade-in-up">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-rose rounded-full animate-pulse" />
              <span className="text-sm text-rose font-medium">正在录音</span>
              <span className="text-sm text-muted-foreground">{formatRecordingTime(recordingDuration)}</span>
            </div>
            <button
              onClick={cancelRecording}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              aria-label="取消录音"
            >
              取消
            </button>
          </div>
        )}
        
        {isProcessing && (
          <div className="flex items-center gap-2 mb-2 px-3 py-2 bg-secondary rounded-lg animate-fade-in-up">
            <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span className="text-sm text-muted-foreground">识别中...</span>
          </div>
        )}

        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2 transition-all focus-within:ring-2 focus-within:ring-primary/30">
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
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && inputValue.trim()) {
                e.preventDefault()
                void submitTurn({ user_message: inputValue.trim() })
              }
            }}
            placeholder={isRecording ? '请说话...' : composerPlaceholder}
            disabled={composerDisabled || isSubmittingTurn || isRecording}
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none disabled:opacity-60"
            aria-label="输入消息"
          />
          
          {/* Voice input button */}
          <button
            aria-label={isRecording ? '停止录音' : '语音输入'}
            onClick={handleVoiceClick}
            disabled={composerDisabled || isSubmittingTurn || isProcessing}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              isRecording
                ? 'bg-rose text-white animate-pulse'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/80'
            )}
          >
            <Mic className="w-5 h-5" />
          </button>
          
          <button
            aria-label="发送消息"
            onClick={() => void submitTurn({ user_message: inputValue.trim() })}
            disabled={composerDisabled || isSubmittingTurn || !inputValue.trim() || isRecording}
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center transition-all',
              inputValue.trim() && !isRecording
                ? 'bg-primary hover:bg-primary/90' 
                : 'bg-muted'
            )}
          >
            {isSubmittingTurn ? (
              <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
            ) : (
              <Send className={cn('w-4 h-4', inputValue.trim() && !isRecording ? 'text-primary-foreground' : 'text-muted-foreground')} />
            )}
          </button>
        </div>
      </div>

    </div>
  )
}

export function RecommendationInbox({
  onViewCandidate,
  onBack,
  onBadgesRefresh,
}: {
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview) => void
  onBack: () => void
  onBadgesRefresh?: () => void
}) {
  const [filter, setFilter] = useState<'all' | 'delayed' | 'matched' | 'interest'>('all')
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [actingCaseId, setActingCaseId] = useState<string | null>(null)  // 正在处理的 case
  const { isLoading, backendItems } = useRecommendationInbox()

  const filteredItems = backendItems.filter((item) => {
    if (dismissedIds.has(item.listKey)) return false
    if (filter === 'delayed') return item.type === 'delayed'
    if (filter === 'matched') return item.type === 'matched'
    if (filter === 'interest') return item.type === 'interest'  // 新增：有人想认识你
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return item.name.toLowerCase().includes(q) || item.city.toLowerCase().includes(q) || item.occupation.toLowerCase().includes(q)
    }
    return true
  })

  // 处理被动推荐卡片的回复
  const handleInterestReply = async (caseId: string, replyType: 'accepted' | 'declined') => {
    if (actingCaseId) return  // 防止重复点击
    setActingCaseId(caseId)
    try {
      await replyProxyIntroCase({
        caseId,
        replyType,
        source: 'recommendation_inbox',
      })
      if (replyType === 'declined') {
        setDismissedIds((prev) => new Set(prev).add(`case:${caseId}`))
      }
      toast.success(replyType === 'accepted' ? '已表达意愿，可以开始聊天了' : '已暂不考虑')
    } catch (error) {
      notifyError(error, replyType === 'accepted' ? '接受失败' : '暂不考虑失败')
    } finally {
      setActingCaseId(null)
    }
  }

  const markRead = async (item: InboxItem) => {
    const profileId = getProfileId()
    if (!profileId || !item.cardId) return
    try {
    await markRecommendationCardsRead(Number(profileId), [item.cardId])
      onBadgesRefresh?.()
    } catch (error) {
      notifyError(error, '标记已读失败')
    }
  }

  const recordAction = async (item: InboxItem, actionType: string) => {
    if (!item.subscriptionId || !item.candidateId) return
    const idem = `${item.subscriptionId}:${item.candidateId}:${actionType}`
    try {
    await postRecommendationAction({
      subscriptionId: item.subscriptionId,
      candidateId: item.candidateId,
      actionType,
      idempotencyKey: idem,
    })
    } catch (error) {
      notifyError(error, '操作失败，请重试')
    }
  }

  return (
    <div className="flex flex-col h-full bg-background">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <div className="flex items-center gap-3">
            <button onClick={onBack} className="w-8 h-8 flex items-center justify-center">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="font-medium">推荐来信</h1>
          </div>
        </div>

        <div className="px-4 pb-3 flex gap-2">
          {[
            { id: 'all' as const, label: '全部' },
            { id: 'delayed' as const, label: '延迟推荐' },
            { id: 'matched' as const, label: '主动撮合' },
            { id: 'interest' as const, label: '有人想认识你' },  // 新增
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${filter === tab.id ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索姓名、城市、职业..."
              className="w-full pl-9 pr-8 py-2 bg-secondary rounded-lg text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {searchQuery ? (
              <button onClick={() => setSearchQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {isLoading ? (
          <>
            <InboxItemSkeleton />
            <InboxItemSkeleton />
            <InboxItemSkeleton />
          </>
        ) : filteredItems.length === 0 ? (
          searchQuery ? <EmptySearchResults keyword={searchQuery} /> : <EmptyRecommendations onRefresh={onBack} />
        ) : (
          filteredItems.map((item) => (
            <div
              key={item.listKey}
              onClick={() => {
                // DEBUG: 调试参数传递
                console.log('[RecommendationInbox] 点击卡片传递的参数:', {
                  item_id: item.id,
                  item_caseId: item.caseId,
                  item_type: item.type,
                  candidate_preview: {
                    id: item.id,
                    caseId: item.caseId,
                    viewType: item.type,
                  },
                })
                void markRead(item)
                onViewCandidate(item.id, {
                  id: item.id,
                  name: item.name,
                  age: item.age,
                  city: item.city,
                  occupation: item.occupation,
                  verified: true,
                  matchScore: item.matchScore,
                  image: item.image,
                  message: item.message,
                  recommendationId: item.recommendationId,
                  subscriptionId: item.subscriptionId,
                  // 新增：传递案件信息，让详情页知道这是被动推荐场景
                  caseId: item.caseId,
                  viewType: item.type, // 'interest' 表示被动推荐
                })
              }}
              className="bg-card border border-border rounded-xl p-3 transition-colors cursor-pointer hover:border-primary/30"
            >
              <div className="flex gap-3">
                <div className="relative w-14 h-14 rounded-lg overflow-hidden shrink-0">
                  <Image src={item.image} alt={item.name} fill className="object-cover" />
                  {!item.isRead ? <div className="absolute top-1 right-1 w-2 h-2 bg-rose rounded-full" /> : null}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{item.name}</span>
                      <span className="text-xs text-muted-foreground">{item.age}岁 · {item.city}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{item.time}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{item.occupation}</p>
                  <p className="text-sm text-foreground mt-1.5 line-clamp-1">{item.message}</p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-border">
                <div className="flex items-center gap-1">
                  <span className={`px-2 py-0.5 rounded text-[10px] ${
                    item.type === 'delayed' ? 'bg-gold/20 text-gold' :
                    item.type === 'interest' ? 'bg-primary/20 text-primary' :
                    'bg-rose/20 text-rose'
                  }`}>
                    {item.conversionStage || (
                      item.type === 'delayed' ? '延迟推荐' :
                      item.type === 'interest' ? '有人想认识你' :
                      '主动撮合'
                    )}
                  </span>
                </div>
                {/* 操作按钮区域 */}
                {item.type === 'interest' ? (
                  // 被动推荐卡片：提示用户点击查看详情
                  <span className="text-xs text-muted-foreground">点击查看完整资料 →</span>
                ) : (
                  // 其他类型卡片：跳过/收藏按钮
                  <div className="flex items-center gap-1">
                    <button
                      aria-label={`跳过${item.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        void recordAction(item, 'skip')
                        setDismissedIds((prev) => new Set(prev).add(item.listKey))
                      }}
                      className="p-1.5 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                    <button
                      aria-label={`收藏${item.name}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        void recordAction(item, 'save')
                        setSavedIds((prev) => {
                          const next = new Set(prev)
                          if (next.has(item.id)) next.delete(item.id)
                          else next.add(item.id)
                          return next
                        })
                      }}
                      className={`p-1.5 transition-colors ${savedIds.has(item.id) ? 'text-gold' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                      <Bookmark className={`w-4 h-4 ${savedIds.has(item.id) ? 'fill-current' : ''}`} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
