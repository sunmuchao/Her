'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, MoreVertical, Send, BadgeCheck, Mic, X, Sparkles, Plus, Video, Image as ImageIcon, Phone } from 'lucide-react'
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
import { getErrorMessage } from '@/lib/api/errors'
import { getChatParticipantId, getAvatarUrl } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError } from '@/lib/notify'
import { DEMO_CHAT_MESSAGES } from '@/lib/fixtures/demo-profiles'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'
import { DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import type { CandidatePreview } from '@/lib/types/candidate'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { VideoCallModal, type CallType } from './video-call-modal'

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
  const [isUploadingImage, setIsUploadingImage] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)

  // 视频通话相关状态
  const [showVideoCall, setShowVideoCall] = useState(false)
  const [videoCallType, setVideoCallType] = useState<'audio' | 'video'>('video')
  const [videoCallId, setVideoCallId] = useState<string | null>(null)

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
        const assistantDm = timelineData.conversations.find(
          (c) => c.conversation.channel_key.startsWith('assistant_dm'),
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
        const assistantDm = timelineData.conversations.find(
          (c) => c.conversation.channel_key === 'assistant_dm',
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
  }, [messages])

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

  // 发送图片消息
  const handleSendImage = async () => {
    if (!selectedImage || !resolvedChatId || isUploadingImage) return
    const authorId = getChatParticipantId()
    if (!authorId) return

    setIsUploadingImage(true)

    try {
      // 压缩图片
      const compressedImage = await compressImage(selectedImage)

      // 上传图片
      const uploadResult = await uploadImage(compressedImage)

      // 发送图片消息
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

      // 乐观更新：添加图片消息到列表
      const tempId = `temp-${Date.now()}`
      const optimisticMessage: Message = {
        id: tempId,
        type: 'sent',
        content: '', // 图片消息没有文本内容
        timestamp: '刚刚',
        mediaType: 'image',
        mediaUrl: uploadResult.mediaUrl,
      }
      setMessages(prev => [...prev, optimisticMessage])

      // 清理选择状态
      handleCancelImage()
    } catch (error) {
      notifyError(error, '图片发送失败')
    } finally {
      setIsUploadingImage(false)
    }
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
          <button
            className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors focus-ring rounded-full"
            aria-label="更多选项"
          >
            <MoreVertical className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-4 space-y-3" role="log" aria-label="聊天消息">
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
              {/* ✅ AI红娘消息特殊样式 */}
              {isAssistant && (
                <div className="max-w-[85%] bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-xl p-3 shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="w-5 h-5 rounded-full overflow-hidden bg-gradient-to-br from-purple-400 to-blue-400">
                      <Image
                        src="/xiaoya-avatar.png"
                        alt="小雅"
                        width={20}
                        height={20}
                        className="object-cover"
                      />
                    </div>
                    <span className="text-xs text-purple-600 font-medium flex items-center gap-1">
                      <Sparkles className="w-3 h-3" />
                      小雅的建议
                    </span>
                  </div>
                  <p className="text-sm text-purple-900 leading-relaxed">{msg.content}</p>
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
              <div className="max-w-[75%]">
                <div className={cn(
                  'px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed',
                  isSent
                    ? 'bg-primary text-primary-foreground rounded-br-md'
                    : 'bg-card border border-border rounded-bl-md'
                )}>
                  {/* 图片消息 */}
                  {msg.mediaType === 'image' && msg.mediaUrl ? (
                    <div className="max-w-[200px]">
                      <img
                        src={msg.mediaUrl}
                        alt="图片消息"
                        className="w-full h-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                        onClick={() => window.open(msg.mediaUrl, '_blank')}
                      />
                    </div>
                  ) : (
                    /* 文本消息 */
                    msg.content
                  )}
                </div>
              </div>
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
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 bg-background border-t border-border safe-area-bottom">
        {/* 小雅私信悬浮面板（输入框上方，不遮挡对话） */}
        {showXiaoyaChat && resolvedCaseId && (
          <div className="flex-shrink-0 px-4 py-3 bg-gradient-to-r from-purple-50/50 to-blue-50/50 animate-slide-down">
            {/* 面板内容 */}
            <div className="bg-white/80 backdrop-blur-sm rounded-xl shadow-sm border border-purple-100">
              {/* 头部 */}
              <div className="flex items-center justify-between px-3 py-2.5 border-b border-purple-100/50">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full overflow-hidden bg-gradient-to-br from-purple-400 to-blue-400 flex items-center justify-center">
                    <Image
                      src="/xiaoya-avatar.png"
                      alt="小雅"
                      width={28}
                      height={28}
                      className="object-cover"
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-medium text-purple-700">小雅 · 私信助手</h3>
                    <p className="text-[10px] text-purple-500/70">对方看不到这些对话</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowXiaoyaChat(false)}
                  className="w-7 h-7 rounded-full hover:bg-purple-100 flex items-center justify-center transition-colors"
                  aria-label="收起"
                >
                  <X className="w-4 h-4 text-purple-600" />
                </button>
              </div>

              {/* 消息列表 - 最多显示3条 */}
              <div className="max-h-[120px] overflow-y-auto px-3 py-2 space-y-2">
                {xiaoyaMessages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-3 gap-2 text-center">
                    <p className="text-xs text-purple-600/80">有什么想悄悄问小雅的吗？</p>
                    <p className="text-[10px] text-purple-400/60">比如：帮我分析下对方说的话</p>
                  </div>
                ) : (
                  xiaoyaMessages.slice(-3).map((msg) => (
                    <div
                      key={msg.id}
                      className={cn('flex', msg.isFromMe ? 'justify-end' : 'justify-start')}
                    >
                      <div
                        className={cn(
                          'max-w-[85%] px-2.5 py-1.5 rounded-xl text-xs',
                          msg.isFromMe
                            ? 'bg-purple-100 text-purple-700 rounded-br-md'
                            : 'bg-secondary text-foreground rounded-bl-md',
                        )}
                      >
                        {msg.body}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 输入框 */}
              <div className="px-3 py-2 border-t border-purple-100/50">
                <div className="flex items-center gap-2 bg-white/60 rounded-lg px-2.5 py-1.5 border border-purple-100/30">
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
                    className="flex-1 bg-transparent text-xs placeholder:text-purple-400/50 focus:outline-none"
                    disabled={!xiaoyaConversationId}
                  />
                  <button
                    type="button"
                    onClick={() => void handleSendXiaoyaMessage()}
                    disabled={!xiaoyaInputValue.trim() || xiaoyaIsSending || !xiaoyaConversationId}
                    className={cn(
                      'w-6 h-6 rounded-full flex items-center justify-center transition-all',
                      xiaoyaInputValue.trim() && !xiaoyaIsSending
                        ? 'bg-purple-500 hover:bg-purple-600'
                        : 'bg-purple-100 cursor-not-allowed',
                    )}
                  >
                    {xiaoyaIsSending ? (
                      <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <Send className={cn('w-3 h-3', xiaoyaInputValue.trim() ? 'text-white' : 'text-purple-300')} />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

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
                  disabled={isUploadingImage}
                  className={cn(
                    'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                    isUploadingImage
                      ? 'bg-muted text-muted-foreground cursor-not-allowed'
                      : 'bg-primary text-primary-foreground hover:bg-primary/90'
                  )}
                >
                  {isUploadingImage ? '发送中...' : '发送图片'}
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
                onClick={() => setShowXiaoyaChat(!showXiaoyaChat)}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-secondary hover:bg-secondary/80 transition-colors"
                aria-label="私信小雅"
              >
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center overflow-hidden">
                  <Image
                    src="/xiaoya-avatar.png"
                    alt="小雅"
                    width={24}
                    height={24}
                    className="object-cover opacity-70"
                  />
                </div>
                <span className="text-xs text-muted-foreground">小雅</span>
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
            {/* 语音按钮（直接显示在输入框旁边） */}
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
    </div>
  )
}
