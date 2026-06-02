'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, MoreVertical, Send, BadgeCheck, Mic, X, Sparkles, Plus, Video, Image as ImageIcon, Phone, MapPin, Smile, User, Star, BellOff, Flag, ChevronDown, RotateCcw } from 'lucide-react'
import Image from 'next/image'
import { cn } from '@/lib/utils'
import { gatewayJson, queryString } from '@/lib/api/client'
import { markConversationRead, fetchPrivateChatConversationId, fetchPrivateMessages, sendPrivateMessage, type PrivateMessage } from '@/lib/api/endpoints/chat'
import { uploadImage, compressImage, getImagePreviewUrl, type UploadMediaResponse } from '@/lib/api/endpoints/media'
import {
  fetchCaseTimeline,
  extractMainGroupMessages,
  type ChatMessageDisplay,
  type CaseTimelineResponse,
} from '@/lib/api/endpoints/chat-timeline'
import { getXiaoyaMessage, markXiaoyaMessageRead } from '@/lib/api/endpoints/assessment'  // 新增
import { getErrorMessage } from '@/lib/api/errors'
import { getChatParticipantId, getAvatarUrl, getProfileId, getUserId } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError } from '@/lib/notify'
import { DEMO_CHAT_MESSAGES } from '@/lib/fixtures/demo-profiles'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'
import { DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import type { CandidatePreview } from '@/lib/types/candidate'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { XiaoyaRichText } from './ui/xiaoya-rich-text'
import { VideoCallModal, type CallType } from './video-call-modal'
import {
  startValuesAuctionTogether,
  type ValuesAuctionCard,
} from '@/lib/api/endpoints/valuesAuction'
import { ValuesAuctionCardRenderer } from '@/components/values-auction'

interface ChatPageProps {
  chatId: string | null
  caseId?: string | null
  counterpartId?: string | null
  counterpartName?: string
  counterpartImage?: string
  onBack: () => void
  onViewCandidate?: (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null, fromChatId?: string) => void
}

type Message = ChatMessageDisplay

type ConversationResponse = {
  conversation: {
    conversation_id: string
    channel_key: string
    members?: Array<{
      participant_id: string
      member_role: string
    }>
  }
}

type MessagesResponse = {
  messages: Array<{
    message_id: number
    author_id: string
    source: string
    body: string
    created_at: string
  }>
}

export default function ChatPage({ chatId, caseId, counterpartId, counterpartName, counterpartImage, onBack, onViewCandidate }: ChatPageProps) {
  const searchParams = useSearchParams()
  const urlChatTitle = searchParams.get('chatTitle')
  const urlCaseId = searchParams.get('caseId')
  console.log('[ChatPage] URL 参数 chatTitle:', urlChatTitle, 'caseId:', urlCaseId)

  // 优先使用 prop 传入的 caseId，其次使用 URL 参数
  const resolvedCaseId = caseId || urlCaseId

  const resolvedChatId = chatId === 'demo' ? DEMO_DEFAULT_CHAT_ID : chatId
  const [inputValue, setInputValue] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [chatTitle, setChatTitle] = useState(urlChatTitle || '聊天')
  const [chatAvatar, setChatAvatar] = useState(PLACEHOLDER_AVATAR)
  const [myAvatar, setMyAvatar] = useState(getAvatarUrl() || PLACEHOLDER_AVATAR)
  const [verified, setVerified] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [showActionMenu, setShowActionMenu] = useState(false)
  const [showXiaoyaChat, setShowXiaoyaChat] = useState(false)
  const [xiaoyaMessages, setXiaoyaMessages] = useState<PrivateMessage[]>([])
  const [xiaoyaInputValue, setXiaoyaInputValue] = useState('')
  const [xiaoyaConversationId, setXiaoyaConversationId] = useState<string | null>(null)
  const [xiaoyaIsSending, setXiaoyaIsSending] = useState(false)
  const xiaoyaMessagesEndRef = useRef<HTMLDivElement>(null)

  // 小雅主动提示相关状态
  const xiaoyaLastCheckTimeRef = useRef<string>('') // 记录上次检查时间，避免重复触发
  const [xiaoyaTriggerReason, setXiaoyaTriggerReason] = useState<string | null>(null)
  const hasAutoOpenedXiaoyaRef = useRef(false) // 是否已自动展开过（避免反复弹出）

  // 图片发送相关状态
  const [selectedImage, setSelectedImage] = useState<File | null>(null)
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)

  // 视频通话相关状态
  const [showVideoCall, setShowVideoCall] = useState(false)
  const [videoCallType, setVideoCallType] = useState<'audio' | 'video'>('video')
  const [videoCallId, setVideoCallId] = useState<string | null>(null)

  // 图片预览模态框状态
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null)
  const [imageScale, setImageScale] = useState(1)
  const lastTapRef = useRef<number>(0)

  // Header 更多菜单状态
  const [showHeaderMenu, setShowHeaderMenu] = useState(false)
  const [valuesAuctionCard, setValuesAuctionCard] = useState<ValuesAuctionCard | null>(null)
  const [valuesAuctionBusy, setValuesAuctionBusy] = useState(false)

  // 新消息提示状态
  const [hasNewMessage, setHasNewMessage] = useState(false)
  const [newMessagePreview, setNewMessagePreview] = useState<{ content: string; avatar: string } | null>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const messagesContainerRef = useRef<HTMLDivElement>(null)

  // 小雅底部面板状态 - 使用具体高度值而非档位，支持流畅拖拽
  const [xiaoyaSheetHeight, setXiaoyaSheetHeight] = useState(300) // 默认300px高度
  const [xiaoyaIsTyping, setXiaoyaIsTyping] = useState(false)
  const xiaoyaDragStartY = useRef(0)
  const xiaoyaDragStartHeight = useRef(300)
  // 最小/最大高度常量（需要在渲染时计算）
  const MIN_SHEET_HEIGHT = 180 // 最小高度
  const MAX_SHEET_HEIGHT = typeof window !== 'undefined' ? window.innerHeight * 0.85 : 600 // 最大高度（85vh）

  // 加载小雅私信会话
  useEffect(() => {
    if (!showXiaoyaChat || !resolvedCaseId) return

    const requesterId = getChatParticipantId()
    if (!requesterId) return

    let cancelled = false
    async function loadXiaoyaChat() {
      try {
        const currentCaseId = resolvedCaseId
        const currentRequesterId = requesterId
        if (!currentCaseId || !currentRequesterId) return

        const convId = await fetchPrivateChatConversationId(currentCaseId, currentRequesterId)
        if (cancelled || !convId) return

        setXiaoyaConversationId(convId)
        const msgs = await fetchPrivateMessages(convId, currentRequesterId)
        if (!cancelled) {
          setXiaoyaMessages(msgs)
        }

        // 新增：检查是否有测评解读消息
        const xiaoyaResult = await getXiaoyaMessage(currentRequesterId)
        if (!cancelled && xiaoyaResult.has_message && xiaoyaResult.message) {
          // 添加小雅解读消息到消息列表
          const assessmentMsg: PrivateMessage = {
            id: `xiaoya-assessment-${Date.now()}`,
            authorId: 'xiaoya',  // 小雅的ID
            body: xiaoyaResult.message,
            createdAt: new Date().toISOString(),
            isFromMe: false,
          }
          setXiaoyaMessages((prev) => [...prev, assessmentMsg])

          // 标记为已读
          if (xiaoyaResult.assessment_id) {
            await markXiaoyaMessageRead(currentRequesterId, xiaoyaResult.assessment_id)
          }
        }
      } catch (error) {
        console.error('[XiaoyaChat] 加载失败:', error)
      }
    }
    void loadXiaoyaChat()
    return () => { cancelled = true }
  }, [showXiaoyaChat, resolvedCaseId])

  // 小雅消息滚动到底部
  useEffect(() => {
    if (showXiaoyaChat) {
      xiaoyaMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [xiaoyaMessages, showXiaoyaChat])

  // 发送小雅私信
  const handleSendXiaoyaMessage = async () => {
    const body = xiaoyaInputValue.trim()
    if (!body || !xiaoyaConversationId || xiaoyaIsSending) return

    const requesterId = getChatParticipantId()
    if (!requesterId) return

    setXiaoyaInputValue('')
    setXiaoyaIsSending(true)

    // 乐观更新
    const tempId = `temp-${Date.now()}`
    const optimisticMsg: PrivateMessage = {
      id: tempId,
      authorId: requesterId,
      body,
      createdAt: new Date().toISOString(),
      isFromMe: true,
    }
    setXiaoyaMessages((prev) => [...prev, optimisticMsg])

    try {
      await sendPrivateMessage(xiaoyaConversationId, requesterId, body)
    } catch (error) {
      setXiaoyaMessages((prev) => prev.filter((m) => m.id !== tempId))
      notifyError(error, '发送失败')
    } finally {
      setXiaoyaIsSending(false)
    }
  }

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const valuesAuctionUserKey = String(getProfileId() || getUserId() || '')
  const valuesAuctionPartnerKey = String(counterpartId || '')

  // 使用 ref 保存最新的 urlChatTitle，避免闭包问题
  const chatTitleRef = useRef(urlChatTitle)
  useEffect(() => {
    chatTitleRef.current = urlChatTitle
    if (urlChatTitle) {
      setChatTitle(urlChatTitle)
    }
  }, [urlChatTitle])

  useEffect(() => {
    if (!resolvedChatId) return
    const resolvedConversationId = resolvedChatId
    const requesterId = getChatParticipantId()
    if (!requesterId) {
      setIsLoading(false)
      setLoadError('未配置 NEXT_PUBLIC_HER_USER_ID')
      if (canUseMockFallback()) {
        setUsingMockData(true)
        setMessages(DEMO_CHAT_MESSAGES)
      }
      return
    }

    let cancelled = false
    async function loadConversation() {
      // TypeScript 类型收窄在 async 函数内不生效，需要显式断言
      const currentRequesterId = requesterId as string
      setIsLoading(true)
      setLoadError(null)
      try {
        // ✅ 使用timeline API加载消息（包含AI红娘主动提示）
        const timelineData = await fetchCaseTimeline(resolvedCaseId || '', currentRequesterId)
        if (cancelled) return

        // 提取main_group会话的消息（用户对话 + AI红娘提示）
        const mappedMessages = extractMainGroupMessages(timelineData, currentRequesterId)
        setMessages(mappedMessages)

        // ✅ 检测 assistant_dm 会话（小雅私信，channel_key 为 assistant_dm_a 或 assistant_dm_b）
        // 需要检查会话成员列表来确定属于当前用户的会话
        const assistantDm = timelineData.conversations.find(
          (c) =>
            c.conversation.channel_key.startsWith('assistant_dm_') &&
            c.conversation.members?.some(
              (m) => m.participant_id === currentRequesterId && m.member_role === 'human',
            ),
        )

        if (assistantDm && assistantDm.messages && assistantDm.messages.length > 0) {
          // 设置会话ID，以便私信功能可用
          setXiaoyaConversationId(assistantDm.conversation.conversation_id)

          // 记录最新消息时间，用于后续轮询判断
          const latestDmMsg = assistantDm.messages[assistantDm.messages.length - 1]
          xiaoyaLastCheckTimeRef.current = latestDmMsg.created_at

          // 如果是聊天前阶段（刚匹配），且有 agent 私信消息，自动展开面板
          if (mappedMessages.length === 0 && latestDmMsg.source === 'agent' && !hasAutoOpenedXiaoyaRef.current) {
            console.log('[ChatPage] 聊天前阶段，检测到小雅私信，自动展开')
            setShowXiaoyaChat(true)
            setXiaoyaTriggerReason('opening_probe')
            hasAutoOpenedXiaoyaRef.current = true
          }
        }

        // 更新聊天标题
        if (!chatTitleRef.current) {
          const mainGroup = timelineData.conversations.find(
            (c) => c.conversation.channel_key === 'main_group',
          )
          const otherMember =
            mainGroup?.conversation.members?.find(
              (member) => member.participant_id !== currentRequesterId && member.member_role !== 'agent',
            )?.participant_id || '对方'
          setChatTitle(otherMember)
        }

        setVerified(true)
        setUsingMockData(false)

        // 标记消息已读
        const latestMessage = mappedMessages[mappedMessages.length - 1]
        if (latestMessage && latestMessage.authorId !== currentRequesterId) {
          markConversationRead(resolvedChatId || '', Number(latestMessage.id))
        }
      } catch (error) {
        if (cancelled) return
        const message = getErrorMessage(error, '聊天加载失败')
        setLoadError(message)
        if (canUseMockFallback()) {
          setUsingMockData(true)
          setMessages(DEMO_CHAT_MESSAGES)
        } else {
          notifyError(error, message)
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void loadConversation()
    return () => {
      cancelled = true
    }
  }, [resolvedChatId])

  // ✅ 轮询更新：每30秒获取最新消息（包括AI红娘的新提示）
  useEffect(() => {
    if (!resolvedCaseId || !resolvedChatId) return
    const requesterId = getChatParticipantId()
    if (!requesterId) return

    const interval = setInterval(async () => {
      try {
        const timelineData = await fetchCaseTimeline(resolvedCaseId || '', requesterId)
        const mappedMessages = extractMainGroupMessages(timelineData, requesterId)

        // 只在有新消息时更新
        if (mappedMessages.length > messages.length) {
          setMessages(mappedMessages)
          // 标记新消息已读
          const latestMessage = mappedMessages[mappedMessages.length - 1]
          if (latestMessage && latestMessage.authorId !== requesterId) {
            markConversationRead(resolvedChatId, Number(latestMessage.id))
          }
        }

        // ✅ 检测 assistant_dm 新消息（小雅私信主动提示）
        // 需要检查会话成员列表来确定属于当前用户的会话
        const assistantDm = timelineData.conversations.find(
          (c) =>
            c.conversation.channel_key.startsWith('assistant_dm_') &&
            c.conversation.members?.some(
              (m) => m.participant_id === requesterId && m.member_role === 'human',
            ),
        )

        if (assistantDm && assistantDm.messages && assistantDm.messages.length > 0 && !hasAutoOpenedXiaoyaRef.current) {
          const latestDmMsg = assistantDm.messages[assistantDm.messages.length - 1]

          // 判断是否是新消息（比上次检查时间更晚）
          if (latestDmMsg.created_at > xiaoyaLastCheckTimeRef.current && latestDmMsg.source === 'agent') {
            console.log('[ChatPage] 检测到小雅新私信:', latestDmMsg.body)

            // 自动展开小雅私信面板
            setShowXiaoyaChat(true)
            setXiaoyaTriggerReason(latestDmMsg.source || 'assistant_dm')
            hasAutoOpenedXiaoyaRef.current = true

            // 更新上次检查时间
            xiaoyaLastCheckTimeRef.current = latestDmMsg.created_at

            // 设置会话ID
            setXiaoyaConversationId(assistantDm.conversation.conversation_id)
          }
        }
      } catch (error) {
        console.error('[ChatPage] 轮询更新失败:', error)
      }
    }, 30000) // 30秒轮询

    return () => clearInterval(interval)
  }, [resolvedCaseId, resolvedChatId, messages.length])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, valuesAuctionCard])

  const clearValuesAuctionCard = () => {
    setValuesAuctionCard(null)
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, 100)
  }

  const openDualValuesAuction = async () => {
    if (!valuesAuctionUserKey || !valuesAuctionPartnerKey || valuesAuctionBusy) return

    setValuesAuctionBusy(true)
    try {
      const next = await startValuesAuctionTogether({
        userKey: valuesAuctionUserKey,
        partnerKey: valuesAuctionPartnerKey,
      })
      setValuesAuctionCard(next)
      setShowActionMenu(false)
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    } catch (error) {
      notifyError(error, '打开双人价值观拍卖失败')
    } finally {
      setValuesAuctionBusy(false)
    }
  }

  const handleSend = async () => {
    const body = inputValue.trim()
    if (!body || !resolvedChatId || isSending) return
    const authorId = getChatParticipantId()
    if (!authorId) return
    
    setInputValue('')
    setIsSending(true)

    // Optimistic update
    const tempId = `temp-${Date.now()}`
    const optimisticMessage: Message = {
      id: tempId,
      type: 'sent',
      content: body,
      timestamp: '刚刚',
    }
    setMessages(prev => [...prev, optimisticMessage])

    try {
      await gatewayJson(`/v2/chat/conversations/${resolvedChatId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          author_id: authorId,
          body,
        }),
      })
    } catch (error) {
      setMessages((prev) => prev.filter((msg) => msg.id !== tempId))
      notifyError(error, '消息发送失败')
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  // 图片选择处理
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // 验证文件类型
    if (!file.type.startsWith('image/')) {
      notifyError(new Error('请选择图片文件'), '文件格式错误')
      return
    }

    // 验证文件大小（最大 10MB）
    if (file.size > 10 * 1024 * 1024) {
      notifyError(new Error('图片大小不能超过 10MB'), '文件过大')
      return
    }

    setSelectedImage(file)
    setImagePreviewUrl(getImagePreviewUrl(file))
    setShowActionMenu(false)
  }

  // 取消图片选择
  const handleCancelImage = () => {
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl)
    }
    setSelectedImage(null)
    setImagePreviewUrl(null)
    if (imageInputRef.current) {
      imageInputRef.current.value = ''
    }
  }

  // 发送图片消息（异步流程：立即显示，后台上传）
  const handleSendImage = () => {
    if (!selectedImage || !resolvedChatId) return
    const authorId = getChatParticipantId()
    if (!authorId) return

    // 1. 立即添加乐观消息（sending 状态，使用本地预览）
    const tempId = `temp-${Date.now()}`
    const localPreviewUrl = getImagePreviewUrl(selectedImage)

    const optimisticMessage: Message = {
      id: tempId,
      type: 'sent',
      content: '',
      timestamp: '刚刚',
      status: 'sending',
      mediaType: 'image',
      mediaUrl: localPreviewUrl,
      localPreviewUrl,
      retryData: { file: selectedImage },
    }
    setMessages(prev => [...prev, optimisticMessage])

    // 2. 清理选择状态，用户可继续操作
    handleCancelImage()

    // 3. 后台异步执行上传（不阻塞 UI）
    processImageUploadAsync(tempId, selectedImage, authorId)
  }

  // 异步处理图片上传流程
  const processImageUploadAsync = async (tempId: string, file: File, authorId: string) => {
    try {
      // 压缩图片
      const compressedImage = await compressImage(file)

      // 上传到 MinIO
      const uploadResult = await uploadImage(compressedImage)

      // 发送消息到会话
      await gatewayJson(`/v2/chat/conversations/${resolvedChatId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          author_id: authorId,
          body: '',
          media_type: 'image',
          media_url: uploadResult.mediaUrl,
          media_metadata: uploadResult.metadata,
        }),
      })

      // 更新消息状态为 sent，替换为真实 URL
      setMessages(prev => prev.map(msg =>
        msg.id === tempId
          ? { ...msg, status: 'sent', mediaUrl: uploadResult.mediaUrl, localPreviewUrl: undefined }
          : msg
      ))
    } catch (error) {
      // 更新消息状态为 failed
      setMessages(prev => prev.map(msg =>
        msg.id === tempId
          ? { ...msg, status: 'failed' }
          : msg
      ))
      notifyError(error, '图片发送失败')
    }
  }

  // 重试发送失败的图片消息
  const retryImageMessage = (message: Message) => {
    if (!message.retryData?.file) return
    const authorId = getChatParticipantId()
    if (!authorId) return

    // 更新状态为 sending
    setMessages(prev => prev.map(msg =>
      msg.id === message.id ? { ...msg, status: 'sending' } : msg
    ))

    // 重新执行上传流程
    processImageUploadAsync(message.id, message.retryData.file, authorId)
  }

  if (isLoading) {
    return (
      <div className="h-full min-h-0 bg-background flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载对话中…</p>
      </div>
    )
  }

  if (loadError && !canUseMockFallback()) {
    return <ErrorState message={loadError} onBack={onBack} />
  }

  return (
    <div className="h-full min-h-0 bg-background flex flex-col overflow-hidden">
      {usingMockData && <DemoDataBanner />}
      {/* Header */}
      <header className="sticky top-0 flex-shrink-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button
            onClick={onBack}
            className="w-8 h-8 flex items-center justify-center focus-ring rounded-full"
            aria-label="返回"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <button
            onClick={() => {
              if (onViewCandidate && counterpartId) {
                const candidate: CandidatePreview = {
                  id: counterpartId,
                  name: chatTitle,
                  image: chatAvatar,
                  caseId: resolvedCaseId || undefined,
                  viewType: 'matched',
                }
                onViewCandidate(counterpartId, candidate, undefined, resolvedChatId || undefined)
              }
            }}
            disabled={!onViewCandidate || !counterpartId}
            className={cn(
              'w-8 h-8 rounded-full overflow-hidden bg-secondary flex items-center justify-center',
              onViewCandidate && counterpartId ? 'cursor-pointer hover:opacity-80 transition-opacity' : 'cursor-default'
            )}
            aria-label={onViewCandidate && counterpartId ? '查看对方资料' : undefined}
          >
            <Image
              src={chatAvatar}
              alt={chatTitle}
              width={32}
              height={32}
              className="object-cover"
            />
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-sm">{chatTitle}</span>
              {verified && <BadgeCheck className="w-4 h-4 text-primary" aria-label="已认证" />}
            </div>
          </div>
          {/* 更多选项按钮 + 下拉菜单 */}
          <div className="relative">
            <button
              onClick={() => setShowHeaderMenu(!showHeaderMenu)}
              className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors focus-ring rounded-full"
              aria-label="更多选项"
              aria-expanded={showHeaderMenu}
              aria-haspopup="menu"
            >
              <MoreVertical className="w-5 h-5" />
            </button>
            {/* 下拉菜单 */}
            {showHeaderMenu && (
              <>
                <div 
                  className="fixed inset-0 z-30" 
                  onClick={() => setShowHeaderMenu(false)}
                  aria-hidden="true"
                />
                <div 
                  className="absolute right-0 top-full mt-1 w-40 bg-card border border-border rounded-xl shadow-lg z-40 py-1 animate-scale-in"
                  role="menu"
                  aria-label="更多选项菜单"
                >
                  <button
                    onClick={() => {
                      if (onViewCandidate && counterpartId) {
                        const candidate: CandidatePreview = {
                          id: counterpartId,
                          name: chatTitle,
                          image: chatAvatar,
                          caseId: resolvedCaseId || undefined,
                          viewType: 'matched',
                        }
                        onViewCandidate(counterpartId, candidate, undefined, resolvedChatId || undefined)
                      }
                      setShowHeaderMenu(false)
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-foreground hover:bg-secondary transition-colors"
                    role="menuitem"
                  >
                    <User className="w-4 h-4 text-muted-foreground" />
                    查看资料
                  </button>
                  <button
                    onClick={() => {
                      // TODO: 设为特别关注
                      setShowHeaderMenu(false)
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-foreground hover:bg-secondary transition-colors"
                    role="menuitem"
                  >
                    <Star className="w-4 h-4 text-muted-foreground" />
                    设为特别关注
                  </button>
                  <button
                    onClick={() => {
                      // TODO: 消息免打扰
                      setShowHeaderMenu(false)
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-foreground hover:bg-secondary transition-colors"
                    role="menuitem"
                  >
                    <BellOff className="w-4 h-4 text-muted-foreground" />
                    消息免打扰
                  </button>
                  <div className="h-px bg-border my-1" role="separator" />
                  <button
                    onClick={() => {
                      // TODO: 举报
                      setShowHeaderMenu(false)
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-destructive hover:bg-secondary transition-colors"
                    role="menuitem"
                  >
                    <Flag className="w-4 h-4" />
                    举报
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* 新消息提示浮动条 */}
      {hasNewMessage && newMessagePreview && !isAtBottom && (
        <div 
          className="sticky top-16 z-10 mx-4 animate-slide-in-right"
          onClick={() => {
            messagesContainerRef.current?.scrollTo({
              top: messagesContainerRef.current.scrollHeight,
              behavior: 'smooth'
            })
            setHasNewMessage(false)
            setNewMessagePreview(null)
          }}
        >
          <button
            className="w-full flex items-center gap-3 bg-card border border-border rounded-xl p-3 shadow-md hover:bg-secondary/50 transition-colors"
            aria-label="跳转到新消息"
          >
            <div className="w-8 h-8 rounded-full overflow-hidden bg-secondary flex-shrink-0">
              <Image
                src={newMessagePreview.avatar}
                alt="新消息"
                width={32}
                height={32}
                className="object-cover"
              />
            </div>
            <div className="flex-1 text-left min-w-0">
              <p className="text-xs text-muted-foreground">新消息</p>
              <p className="text-sm text-foreground truncate">{newMessagePreview.content}</p>
            </div>
            <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />
          </button>
        </div>
      )}

      {/* Messages */}
      <div 
        ref={messagesContainerRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-4 space-y-3" 
        role="log" 
        aria-label="聊天消息"
        aria-live="polite"
        onScroll={(e) => {
          const container = e.currentTarget
          const isBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50
          setIsAtBottom(isBottom)
          if (isBottom) {
            setHasNewMessage(false)
            setNewMessagePreview(null)
          }
        }}
      >
        {messages.map((msg, index) => {
          const isSent = msg.type === 'sent'
          const isAssistant = msg.type === 'assistant'
          const prevMsg = messages[index - 1]
          // 显示头像的条件：第一条消息，或上一条是对方发的（切换发送者时显示头像）
          const showAvatar = index === 0 || prevMsg?.type !== msg.type

          return (
            <div
              key={msg.id}
              className={cn(
                'flex animate-fade-in-up',
                isAssistant ? 'justify-center' : isSent ? 'justify-end items-end gap-2' : 'justify-start items-end gap-2',
              )}
              style={{ animationDelay: `${index * 30}ms` }}
            >
              {/* AI红娘消息 - 低调辅助样式，不喧宾夺主 */}
                              {isAssistant && (
                                <div className="max-w-[85%] bg-secondary/50 border border-border/60 rounded-xl p-3">
                                  <div className="flex items-center gap-2 mb-1.5">
                                    <div className="w-4 h-4 rounded-full overflow-hidden bg-muted">
                                      <Image
                                        src="/xiaoya-avatar.png"
                                        alt="小雅"
                                        width={16}
                                        height={16}
                                        className="object-cover opacity-70"
                                      />
                                    </div>
                                    <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                                      <Sparkles className="w-2.5 h-2.5" />
                                      小雅提示
                                    </span>
                                  </div>
                                  <XiaoyaRichText content={msg.content} />
                                </div>
                              )}

              {/* 用户消息 */}
              {!isAssistant && !isSent && (
                <div className={cn('w-8 h-8 rounded-full overflow-hidden bg-secondary flex-shrink-0', showAvatar ? 'opacity-100' : 'opacity-0')}>
                  <Image
                    src={chatAvatar}
                    alt={chatTitle}
                    width={32}
                    height={32}
                    className="object-cover"
                  />
                </div>
              )}
              {/* ✅ 气泡框只对用户消息显示，不对小雅消息显示 */}
              {!isAssistant && (
                <div className="max-w-[75%]">
                  <div className={cn(
                    'px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed',
                    isSent
                      ? 'bg-primary text-primary-foreground rounded-br-md'
                      : 'bg-card border border-border rounded-bl-md'
                  )}>
                    {/* 图片消息 - 支持长按预览、双击放大、状态覆盖层 */}
                    {msg.mediaType === 'image' && msg.mediaUrl ? (
                      <div
                        className="max-w-[200px] relative"
                        onContextMenu={(e) => {
                          e.preventDefault()
                          setPreviewImageUrl(msg.mediaUrl || null)
                          setImageScale(1)
                        }}
                        onClick={() => {
                          // failed 状态不触发预览
                          if (msg.status === 'failed') return
                          const now = Date.now()
                          const timeSinceLastTap = now - lastTapRef.current
                          if (timeSinceLastTap < 300) {
                            // 双击放大
                            setPreviewImageUrl(msg.mediaUrl || null)
                            setImageScale(2)
                          }
                          lastTapRef.current = now
                        }}
                        onTouchStart={(e) => {
                          // failed 状态不触发长按
                          if (msg.status === 'failed') return
                          const touchTimer = setTimeout(() => {
                            setPreviewImageUrl(msg.mediaUrl || null)
                            setImageScale(1)
                          }, 500)
                          const handleTouchEnd = () => {
                            clearTimeout(touchTimer)
                            e.currentTarget.removeEventListener('touchend', handleTouchEnd)
                          }
                          e.currentTarget.addEventListener('touchend', handleTouchEnd)
                        }}
                      >
                        <img
                          src={msg.mediaUrl}
                          alt="图片消息"
                          className={cn(
                            "w-full h-auto rounded-lg select-none",
                            msg.status === 'sending' || msg.status === 'failed'
                              ? 'opacity-70'
                              : 'cursor-pointer hover:opacity-90 transition-opacity'
                          )}
                          draggable={false}
                        />
                        {/* sending 状态显示加载动画 */}
                        {msg.status === 'sending' && (
                          <div className="absolute inset-0 flex items-center justify-center bg-black/20 rounded-lg">
                            <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin" />
                          </div>
                        )}
                        {/* failed 状态显示重试按钮 */}
                        {msg.status === 'failed' && (
                          <div
                            className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg cursor-pointer"
                            onClick={(e) => {
                              e.stopPropagation()
                              retryImageMessage(msg)
                            }}
                          >
                            <div className="w-8 h-8 rounded-full bg-white/90 flex items-center justify-center">
                              <RotateCcw className="w-4 h-4 text-primary" />
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      /* 文本消息 */
                      msg.content
                    )}
                  </div>
                </div>
              )}
              {!isAssistant && isSent && (
                <div className={cn('w-8 h-8 rounded-full overflow-hidden bg-secondary flex-shrink-0', showAvatar ? 'opacity-100' : 'opacity-0')}>
                  <Image
                    src={myAvatar}
                    alt="我"
                    width={32}
                    height={32}
                    className="object-cover"
                  />
                </div>
              )}
            </div>
          )
        })}

        {valuesAuctionCard ? (
          <div className="flex justify-center">
            <div className="w-full max-w-[92%]">
              <ValuesAuctionCardRenderer
                card={valuesAuctionCard}
                userKey={valuesAuctionUserKey}
                onContinue={clearValuesAuctionCard}
              />
            </div>
          </div>
        ) : null}

        <div ref={messagesEndRef} />
      </div>

      {/* 小雅私信底部面板 - 可拖动调整高���，支持全屏模式 */}
      {showXiaoyaChat && resolvedCaseId && (
        <div 
          className="fixed inset-0 z-50 flex flex-col justify-end"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowXiaoyaChat(false)
            }
          }}
        >
          {/* 背景遮罩 */}
          <div className="absolute inset-0 bg-black/30 animate-fade-in" />
          
          {/* 底部面板 - 固定在底部，拖拽上边缘调整高度 */}
          <div
            className="relative bg-background rounded-t-2xl shadow-xl animate-slide-up flex flex-col"
            style={{ height: `${xiaoyaSheetHeight}px` }}
          >
            {/* 拖动上边缘 - 整个头部区域可拖拽 */}
            <div
              className="flex flex-col cursor-grab active:cursor-grabbing touch-none select-none"
              onPointerDown={(e) => {
                xiaoyaDragStartY.current = e.clientY
                xiaoyaDragStartHeight.current = xiaoyaSheetHeight
                e.currentTarget.setPointerCapture(e.pointerId)
              }}
              onPointerMove={(e) => {
                if (!e.currentTarget.hasPointerCapture(e.pointerId)) return
                const delta = xiaoyaDragStartY.current - e.clientY
                const newHeight = Math.max(MIN_SHEET_HEIGHT, Math.min(MAX_SHEET_HEIGHT, xiaoyaDragStartHeight.current + delta))
                setXiaoyaSheetHeight(newHeight)
              }}
              onPointerUp={(e) => {
                e.currentTarget.releasePointerCapture(e.pointerId)
              }}
            >
              {/* 拖动指示条 */}
              <div className="flex justify-center py-2">
                <div className="w-10 h-1 rounded-full bg-border" />
              </div>

              {/* 头部 - 使用 gold 主题色 */}
              <div className="flex items-center justify-between px-4 pb-3 border-b border-border">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full overflow-hidden bg-gradient-to-br from-gold to-gold/70 flex items-center justify-center">
                    <Image
                      src="/xiaoya-avatar.png"
                      alt="小雅"
                      width={36}
                      height={36}
                      className="object-cover"
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-foreground">小雅 · 私信助手</h3>
                    <p className="text-[10px] text-muted-foreground">
                      {xiaoyaIsTyping ? (
                        <span className="flex items-center gap-1 text-gold">
                          正在输入
                          <span className="flex gap-0.5">
                            <span className="w-1 h-1 rounded-full bg-gold animate-bounce-dot" style={{ animationDelay: '0ms' }} />
                            <span className="w-1 h-1 rounded-full bg-gold animate-bounce-dot" style={{ animationDelay: '150ms' }} />
                            <span className="w-1 h-1 rounded-full bg-gold animate-bounce-dot" style={{ animationDelay: '300ms' }} />
                          </span>
                        </span>
                      ) : (
                        '对方看不到这些对话'
                      )}
                    </p>
                  </div>
                </div>
                {/* 关闭按钮 */}
                <button
                  type="button"
                  onClick={() => setShowXiaoyaChat(false)}
                  className="w-8 h-8 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
                  aria-label="关闭"
                >
                  <X className="w-4 h-4 text-muted-foreground" />
                </button>
              </div>
            </div>

            {/* 消息列表 - 支持滚动，动态高度 */}
            <div
              className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0"
              style={{ maxHeight: `${xiaoyaSheetHeight - 140}px` }}
            >
              {xiaoyaMessages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 gap-3 text-center">
                  <div className="w-16 h-16 rounded-full bg-gold-soft flex items-center justify-center">
                    <Sparkles className="w-8 h-8 text-gold" />
                  </div>
                  <div>
                    <p className="text-sm text-foreground">有什么想悄悄问小雅的吗？</p>
                    <p className="text-xs text-muted-foreground mt-1">比如：帮我分析下对方说的话</p>
                  </div>
                </div>
              ) : (
                <>
                  {xiaoyaMessages.map((msg, index) => {
                    // 时间分割线逻辑
                    const showDateDivider = index === 0 || (() => {
                      const prevDate = new Date(xiaoyaMessages[index - 1]?.createdAt || '').toDateString()
                      const currDate = new Date(msg.createdAt).toDateString()
                      return prevDate !== currDate
                    })()
                    
                    return (
                      <div key={msg.id}>
                        {/* 时间分割线 */}
                        {showDateDivider && (
                          <div className="flex items-center gap-3 py-2">
                            <div className="flex-1 h-px bg-border" />
                            <span className="text-[10px] text-muted-foreground">
                              {new Date(msg.createdAt).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                            </span>
                            <div className="flex-1 h-px bg-border" />
                          </div>
                        )}
                        <div className={cn('flex', msg.isFromMe ? 'justify-end' : 'justify-start')}>
                          {!msg.isFromMe && (
                            <div className="w-7 h-7 rounded-full overflow-hidden bg-gradient-to-br from-gold to-gold/70 mr-2 flex-shrink-0">
                              <Image src="/xiaoya-avatar.png" alt="小雅" width={28} height={28} className="object-cover" />
                            </div>
                          )}
                          <div
                            className={cn(
                              'max-w-[75%] px-3 py-2 rounded-2xl text-sm whitespace-pre-line',
                              msg.isFromMe
                                ? 'bg-gold text-white rounded-br-md'
                                : 'bg-secondary text-foreground rounded-bl-md',
                            )}
                          >
                            {msg.body}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                  <div ref={xiaoyaMessagesEndRef} />
                </>
              )}
            </div>

            {/* 输入框 - 使用 gold 主题色 */}
            <div className="px-4 py-3 border-t border-border bg-background">
              <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
                {/* 表情面板入口 */}
                <button
                  type="button"
                  className="w-8 h-8 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  aria-label="表情"
                >
                  <Smile className="w-5 h-5" />
                </button>
                <input
                  value={xiaoyaInputValue}
                  onChange={(e) => setXiaoyaInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      void handleSendXiaoyaMessage()
                    }
                  }}
                  placeholder="跟小雅说点悄悄话..."
                  className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
                  disabled={!xiaoyaConversationId}
                  aria-label="输入私信内容"
                />
                <button
                  type="button"
                  onClick={() => void handleSendXiaoyaMessage()}
                  disabled={!xiaoyaInputValue.trim() || xiaoyaIsSending || !xiaoyaConversationId}
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                    xiaoyaInputValue.trim() && !xiaoyaIsSending
                      ? 'bg-gold hover:bg-gold/90'
                      : 'bg-muted cursor-not-allowed',
                  )}
                  aria-label={xiaoyaIsSending ? '发送中' : '发送'}
                >
                  {xiaoyaIsSending ? (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <Send className={cn('w-4 h-4', xiaoyaInputValue.trim() ? 'text-white' : 'text-muted-foreground')} />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 bg-background border-t border-border safe-area-bottom">

        {/* 隐藏的文件输入 */}
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleImageSelect}
        />

        {/* 图片预览区域 */}
        {imagePreviewUrl && selectedImage && (
          <div className="px-4 py-3 bg-background animate-fade-in-up">
            <div className="relative bg-secondary rounded-xl p-3">
              <div className="flex items-center gap-3">
                {/* 预览图片 */}
                <div className="w-20 h-20 rounded-lg overflow-hidden bg-muted flex-shrink-0">
                  <img
                    src={imagePreviewUrl}
                    alt="预览"
                    className="w-full h-full object-cover"
                  />
                </div>
                {/* 文件信息 */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{selectedImage.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(selectedImage.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                {/* 取消按钮 */}
                <button
                  onClick={handleCancelImage}
                  className="w-8 h-8 rounded-full bg-muted hover:bg-muted/80 flex items-center justify-center"
                  aria-label="取消"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              {/* 发送按钮 */}
              <div className="mt-3 flex justify-end">
                <button
                  onClick={() => void handleSendImage()}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all"
                >
                  发送图片
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 加号弹出菜单 */}
        {showActionMenu && !imagePreviewUrl && (
          <div
            className="px-4 py-3 bg-background animate-fade-in-up"
            onClick={(e) => {
              // 点击背景关闭菜单，但不关闭文件输入弹出的选择窗口
              if (e.target === e.currentTarget) {
                setShowActionMenu(false)
              }
            }}
          >
            <div className="grid grid-cols-4 gap-4">
              {/* 图片 */}
              <button
                onClick={() => imageInputRef.current?.click()}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-label="发送图片"
              >
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <ImageIcon className="w-6 h-6 text-primary" />
                </div>
                <span className="text-xs text-foreground">图片</span>
              </button>
              {/* 视频通话 */}
              <button
                onClick={() => {
                  setVideoCallType('video')
                  setVideoCallId(`call-${Date.now()}`)
                  setShowVideoCall(true)
                  setShowActionMenu(false)
                }}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-label="视频通话"
              >
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <Video className="w-6 h-6 text-primary" />
                </div>
                <span className="text-xs text-foreground">视频</span>
              </button>
              {/* 语音通话 */}
              <button
                onClick={() => {
                  setVideoCallType('audio')
                  setVideoCallId(`call-${Date.now()}`)
                  setShowVideoCall(true)
                  setShowActionMenu(false)
                }}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-label="语音通话"
              >
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <Phone className="w-6 h-6 text-primary" />
                </div>
                <span className="text-xs text-foreground">语音</span>
              </button>
              {/* 小雅助手 */}
              <button
                onClick={() => {
                  setShowXiaoyaChat(!showXiaoyaChat)
                  setShowActionMenu(false)
                }}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-label="私信小雅"
              >
                <div className="w-12 h-12 rounded-full bg-gold-soft flex items-center justify-center overflow-hidden">
                  <Image
                    src="/xiaoya-avatar.png"
                    alt="小雅"
                    width={24}
                    height={24}
                    className="object-cover"
                  />
                </div>
                <span className="text-xs text-gold">小雅</span>
              </button>
              {/* 双人价值观拍卖 */}
              <button
                onClick={() => {
                  void openDualValuesAuction()
                }}
                disabled={!valuesAuctionUserKey || !valuesAuctionPartnerKey || valuesAuctionBusy}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors disabled:opacity-60"
                aria-label="双人价值观拍卖"
              >
                <div className="w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center">
                  <Sparkles className="w-6 h-6 text-amber-600" />
                </div>
                <span className="text-xs text-foreground">价值观拍卖</span>
              </button>
              {/* 位置分享 */}
              <button
                onClick={() => {
                  // TODO: 位置分享功能
                  setShowActionMenu(false)
                }}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-label="分享位置"
              >
                <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <MapPin className="w-6 h-6 text-primary" />
                </div>
                <span className="text-xs text-foreground">位置</span>
              </button>
            </div>
          </div>
        )}

        {/* 输入框区域 */}
        <div className="px-4 py-3">
          <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2 transition-all focus-within:ring-2 focus-within:ring-primary/30">
            {/* 加号按钮 */}
            <button
              aria-label={showActionMenu ? '收起菜单' : '展开菜单'}
              onClick={() => setShowActionMenu(!showActionMenu)}
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                showActionMenu
                  ? 'bg-primary text-primary-foreground rotate-45'
                  : 'bg-muted hover:bg-primary/10',
              )}
            >
              <Plus className="w-5 h-5" />
            </button>
            {/* 表情按钮 */}
            <button
              aria-label="表情"
              className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
            >
              <Smile className="w-5 h-5" />
            </button>
            {/* 语音按钮 */}
            <button
              aria-label="语音输入（即将上线）"
              className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              disabled
            >
              <Mic className="w-5 h-5" />
            </button>
            {/* 输入框 */}
            <input
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => setShowActionMenu(false)}
              placeholder="输入消息..."
              className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
              aria-label="输入消息"
            />
            {/* 发送按钮 */}
            <button
              aria-label={isSending ? '发送中' : '发送消息'}
              onClick={() => void handleSend()}
              disabled={!inputValue.trim() || isSending}
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                inputValue.trim() && !isSending
                  ? 'bg-primary hover:bg-primary/90'
                  : 'bg-muted cursor-not-allowed'
              )}
            >
              {isSending ? (
                <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
              ) : (
                <Send className={cn('w-4 h-4', inputValue.trim() ? 'text-primary-foreground' : 'text-muted-foreground')} />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 视频通话弹窗 */}
      {showVideoCall && videoCallId && resolvedCaseId && (
        <VideoCallModal
          callId={videoCallId}
          callerId={getChatParticipantId() || ''}
          calleeId={counterpartId || ''}
          callType={videoCallType}
          callerName="我"
          callerAvatar={myAvatar}
          calleeName={chatTitle}
          calleeAvatar={chatAvatar}
          isInitiator={true}
          userId={getChatParticipantId() || ''}
          signalingServerUrl={process.env.NEXT_PUBLIC_SIGNALING_SERVER_URL || 'ws://localhost:8080'}
          onClose={() => {
            setShowVideoCall(false)
            setVideoCallId(null)
          }}
        />
      )}

      {/* 图片预览模态框 - 支持缩放和拖动 */}
      {previewImageUrl && (
        <div 
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center animate-fade-in"
          onClick={() => {
            setPreviewImageUrl(null)
            setImageScale(1)
          }}
          role="dialog"
          aria-modal="true"
          aria-label="图片预览"
        >
          <button
            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition-colors z-10"
            onClick={() => {
              setPreviewImageUrl(null)
              setImageScale(1)
            }}
            aria-label="关闭预览"
          >
            <X className="w-6 h-6 text-white" />
          </button>
          <img
            src={previewImageUrl}
            alt="图片预览"
            className="max-w-[90vw] max-h-[90vh] object-contain transition-transform duration-200"
            style={{ transform: `scale(${imageScale})` }}
            onClick={(e) => {
              e.stopPropagation()
              setImageScale(imageScale === 1 ? 2 : 1)
            }}
            draggable={false}
          />
          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-4">
            <button
              className="px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 text-white text-sm transition-colors"
              onClick={(e) => {
                e.stopPropagation()
                setImageScale(Math.max(0.5, imageScale - 0.5))
              }}
              aria-label="缩小"
            >
              缩小
            </button>
            <span className="text-white text-sm">{Math.round(imageScale * 100)}%</span>
            <button
              className="px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 text-white text-sm transition-colors"
              onClick={(e) => {
                e.stopPropagation()
                setImageScale(Math.min(3, imageScale + 0.5))
              }}
              aria-label="放大"
            >
              放大
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
