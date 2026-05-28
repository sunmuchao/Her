'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, Phone, MoreVertical, Send, Image as ImageIcon, BadgeCheck, Mic, MessageCircle, X } from 'lucide-react'
import Image from 'next/image'
import { cn } from '@/lib/utils'
import { gatewayJson, queryString } from '@/lib/api/client'
import { markConversationRead, fetchPrivateChatConversationId, fetchPrivateMessages, sendPrivateMessage, type PrivateMessage } from '@/lib/api/endpoints/chat'
import { getErrorMessage } from '@/lib/api/errors'
import { getChatParticipantId, getAvatarUrl } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError } from '@/lib/notify'
import { DEMO_CHAT_MESSAGES } from '@/lib/fixtures/demo-profiles'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'
import { DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'

interface ChatPageProps {
  chatId: string | null
  caseId?: string | null
  onBack: () => void
}

type Message = {
  id: string
  type: 'sent' | 'received'
  content: string
  timestamp: string
}

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


// 私信悬浮球和弹窗组件
function PrivateChatFab({
  caseId,
  requesterId,
}: {
  caseId: string
  requesterId: string
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<PrivateMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [hasUnread, setHasUnread] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 加载私信会话
  useEffect(() => {
    if (!isOpen || !caseId || !requesterId) return

    let cancelled = false
    async function load() {
      setIsLoading(true)
      try {
        const convId = await fetchPrivateChatConversationId(caseId, requesterId)
        if (cancelled || !convId) {
          setIsLoading(false)
          return
        }
        setConversationId(convId)
        const msgs = await fetchPrivateMessages(convId, requesterId)
        if (!cancelled) {
          setMessages(msgs)
          setHasUnread(false)
        }
      } catch (error) {
        if (!cancelled) {
          notifyError(error, '加载私信失败')
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [isOpen, caseId, requesterId])

  // 滚动到底部
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen])

  const handleSend = async () => {
    const body = inputValue.trim()
    if (!body || !conversationId || isSending) return

    setInputValue('')
    setIsSending(true)

    // 乐观更新
    const tempId = `temp-${Date.now()}`
    const optimisticMsg: PrivateMessage = {
      id: tempId,
      authorId: requesterId,
      body,
      createdAt: new Date().toISOString(),
      isFromMe: true,
    }
    setMessages((prev) => [...prev, optimisticMsg])

    try {
      await sendPrivateMessage(conversationId, requesterId, body)
    } catch (error) {
      setMessages((prev) => prev.filter((m) => m.id !== tempId))
      notifyError(error, '发送失败')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <>
      {/* 悬浮球 */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={cn(
          'fixed bottom-24 right-4 z-30 w-14 h-14 rounded-full bg-primary shadow-lg flex items-center justify-center transition-transform hover:scale-105 active:scale-95',
          isOpen && 'hidden',
        )}
        aria-label="私信小C"
      >
        <MessageCircle className="w-6 h-6 text-primary-foreground" />
        {hasUnread && (
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-rose rounded-full animate-pulse" />
        )}
      </button>

      {/* 私信弹窗 */}
      {isOpen && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/30 animate-fade-in">
          <div
            className="w-full max-w-md bg-background rounded-t-2xl shadow-2xl flex flex-col animate-slide-up"
            style={{ maxHeight: '70vh' }}
          >
            {/* 弹窗头部 */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                  <MessageCircle className="w-4 h-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-medium">私信小C</h3>
                  <p className="text-[10px] text-muted-foreground">对方看不到这里的消息</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="w-8 h-8 rounded-full hover:bg-secondary flex items-center justify-center"
                aria-label="关闭"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 消息列表 */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[200px]">
              {isLoading ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-muted-foreground">加载中...</p>
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-center">
                  <MessageCircle className="w-10 h-10 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">有什么想悄悄跟小C说的？</p>
                  <p className="text-xs text-muted-foreground/70">比如：帮我问问对方的兴趣爱好</p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      'flex',
                      msg.isFromMe ? 'justify-end' : 'justify-start',
                    )}
                  >
                    <div
                      className={cn(
                        'max-w-[80%] px-3 py-2 rounded-2xl text-sm',
                        msg.isFromMe
                          ? 'bg-primary text-primary-foreground rounded-br-md'
                          : 'bg-secondary rounded-bl-md',
                      )}
                    >
                      {msg.body}
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* 输入框 */}
            <div className="px-4 py-3 border-t border-border safe-area-bottom">
              <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
                <input
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      void handleSend()
                    }
                  }}
                  placeholder="跟小C说点悄悄话..."
                  className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
                  disabled={!conversationId || isLoading}
                />
                <button
                  type="button"
                  onClick={() => void handleSend()}
                  disabled={!inputValue.trim() || isSending || !conversationId}
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center transition-all',
                    inputValue.trim() && !isSending
                      ? 'bg-primary hover:bg-primary/90'
                      : 'bg-muted cursor-not-allowed',
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
        </div>
      )}
    </>
  )
}

export default function ChatPage({ chatId, caseId, onBack }: ChatPageProps) {
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
      setIsLoading(true)
      setLoadError(null)
      try {
        const [conversationData, messageData] = await Promise.all([
          gatewayJson<ConversationResponse>(
            `/v2/chat/conversations/${resolvedChatId}${queryString({ requester_id: requesterId })}`,
          ),
          gatewayJson<MessagesResponse>(
            `/v2/chat/conversations/${resolvedChatId}/messages${queryString({ requester_id: requesterId })}`,
          ),
        ])
        if (cancelled) return
        // 只有在没有 URL 参数 chatTitle 时才从 API 获取标题
        if (!chatTitleRef.current) {
          const otherMember =
            conversationData.conversation.members?.find(
              (member) => member.participant_id !== requesterId && member.member_role !== 'agent',
            )?.participant_id || '对方'
          setChatTitle(otherMember)
        }
        setVerified(true)
        setMessages(
          messageData.messages.map((message) => ({
            id: String(message.message_id),
            type: message.author_id === requesterId ? 'sent' : 'received',
            content: message.body,
            timestamp: message.created_at,
          })),
        )
        const latestMessage = messageData.messages[messageData.messages.length - 1]
        if (latestMessage && latestMessage.author_id !== requesterId) {
          markConversationRead(resolvedConversationId, Number(latestMessage.message_id))
        }
        setUsingMockData(false)
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
          <div className="w-8 h-8 rounded-full overflow-hidden bg-secondary flex items-center justify-center">
            <Image
              src={chatAvatar}
              alt={chatTitle}
              width={32}
              height={32}
              className="object-cover"
            />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-sm">{chatTitle}</span>
              {verified && <BadgeCheck className="w-4 h-4 text-primary" aria-label="已认证" />}
            </div>
          </div>
          <button 
            className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors focus-ring rounded-full"
            aria-label="语音通话（即将上线）"
            disabled
          >
            <Phone className="w-5 h-5" />
          </button>
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
          const prevMsg = messages[index - 1]
          // 显示头像的条件：第一条消息，或上一条是对方发的（切换发送者时显示头像）
          const showAvatar = index === 0 || prevMsg?.type !== msg.type

          return (
            <div
              key={msg.id}
              className={cn('flex animate-fade-in-up', isSent ? 'justify-end items-end gap-2' : 'justify-start items-end gap-2')}
              style={{ animationDelay: `${index * 30}ms` }}
            >
              {!isSent && (
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
                  {msg.content}
                </div>
                              </div>
              {isSent && (
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
      <div className="flex-shrink-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2 transition-all focus-within:ring-2 focus-within:ring-primary/30">
          <button 
            aria-label="发送图片（即将上线）" 
            className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            disabled
          >
            <ImageIcon className="w-5 h-5" />
          </button>
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
            aria-label="输入消息"
          />
          <button 
            aria-label="语音输入（即将上线）" 
            className="w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            disabled
          >
            <Mic className="w-5 h-5" />
          </button>
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

      {/* 私信悬浮球 */}
      {resolvedCaseId && (
        <PrivateChatFab
          caseId={resolvedCaseId}
          requesterId={getChatParticipantId() || ''}
        />
      )}
    </div>
  )
}
