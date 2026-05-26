'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Phone, MoreVertical, Send, Image as ImageIcon, BadgeCheck, Mic, Check, CheckCheck, Clock } from 'lucide-react'
import Image from 'next/image'
import { ChatTypingIndicator } from './ui/typing-indicator'
import { cn } from '@/lib/utils'
import { gatewayJson, queryString } from '@/lib/api/client'
import { getErrorMessage } from '@/lib/api/errors'
import { getChatParticipantId } from '@/lib/auth/session'
import { canUseMockFallback } from '@/lib/mock'
import { notifyError } from '@/lib/notify'
import { DEMO_CHAT_MESSAGES } from '@/lib/fixtures/demo-profiles'
import { PLACEHOLDER_AVATAR } from '@/lib/image-url'
import { DEMO_DEFAULT_CHAT_ID } from '@/lib/navigation/defaults'
import { DemoDataBanner } from './ui/demo-data-banner'
import { ErrorState } from './ui/error-state'
import { EmptyConversations } from './ui/empty-states'

interface ChatPageProps {
  chatId: string | null
  onBack: () => void
}

type MessageStatus = 'sending' | 'sent' | 'delivered' | 'read'

type Message = {
  id: string
  type: 'sent' | 'received'
  content: string
  timestamp: string
  status?: MessageStatus
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

function formatTime(timestamp: string): string {
  if (!timestamp || timestamp === '刚刚') return '刚刚'
  
  try {
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
    
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return timestamp
  }
}

// Message status indicator component
function MessageStatusIndicator({ status }: { status?: MessageStatus }) {
  if (!status) return null
  
  switch (status) {
    case 'sending':
      return <Clock className="w-3 h-3 text-muted-foreground" aria-label="发送中" />
    case 'sent':
      return <Check className="w-3 h-3 text-muted-foreground" aria-label="已发送" />
    case 'delivered':
      return <CheckCheck className="w-3 h-3 text-muted-foreground" aria-label="已送达" />
    case 'read':
      return <CheckCheck className="w-3 h-3 text-primary" aria-label="已读" />
    default:
      return null
  }
}

export default function ChatPage({ chatId, onBack }: ChatPageProps) {
  const resolvedChatId = chatId === 'demo' ? DEMO_DEFAULT_CHAT_ID : chatId
  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [chatTitle, setChatTitle] = useState('聊天')
  const [verified, setVerified] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [usingMockData, setUsingMockData] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!resolvedChatId) return
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
        const otherMember =
          conversationData.conversation.members?.find(
            (member) => member.participant_id !== requesterId && member.member_role !== 'agent',
          )?.participant_id || '对方'
        setChatTitle(otherMember)
        setVerified(true)
        setMessages(
          messageData.messages.map((message, index, arr) => ({
            id: String(message.message_id),
            type: message.author_id === requesterId ? 'sent' : 'received',
            content: message.body,
            timestamp: message.created_at,
            status: message.author_id === requesterId 
              ? (index === arr.length - 1 ? 'read' : 'delivered')
              : undefined,
          })),
        )
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
  }, [isTyping, messages])

  const handleSend = async () => {
    const body = inputValue.trim()
    if (!body || !resolvedChatId || isSending) return
    const authorId = getChatParticipantId()
    if (!authorId) return
    
    setInputValue('')
    setIsSending(true)
    
    // Optimistic update - add message with 'sending' status
    const tempId = `temp-${Date.now()}`
    const optimisticMessage: Message = {
      id: tempId,
      type: 'sent',
      content: body,
      timestamp: '刚刚',
      status: 'sending'
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
      
      // Update message status to sent
      setMessages(prev => prev.map(msg => 
        msg.id === tempId ? { ...msg, status: 'sent' as const } : msg
      ))
      
      // Simulate delivery after short delay
      setTimeout(() => {
        setMessages(prev => prev.map(msg => 
          msg.id === tempId ? { ...msg, status: 'delivered' as const } : msg
        ))
      }, 500)
      
      // Show typing indicator
      setIsTyping(true)
      setTimeout(() => {
        setIsTyping(false)
        // Mark as read when they "respond"
        setMessages(prev => prev.map(msg => 
          msg.id === tempId ? { ...msg, status: 'read' as const } : msg
        ))
      }, 1500)
      
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
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载对话中…</p>
      </div>
    )
  }

  if (loadError && !canUseMockFallback()) {
    return <ErrorState message={loadError} onBack={onBack} />
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {usingMockData && <DemoDataBanner />}
      {/* Header */}
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
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
              src={PLACEHOLDER_AVATAR}
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
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3" role="log" aria-label="聊天消息">
        {messages.length === 0 && !isTyping ? (
          <EmptyConversations />
        ) : (
          messages.map((msg, index) => {
          const isSent = msg.type === 'sent'
          const showTime = index === 0 || 
            messages[index - 1]?.type !== msg.type ||
            (index > 0 && msg.timestamp !== messages[index - 1]?.timestamp)
          
          return (
            <div 
              key={msg.id} 
              className={cn('flex animate-fade-in-up', isSent ? 'justify-end' : 'justify-start')}
              style={{ animationDelay: `${index * 30}ms` }}
            >
              <div className="max-w-[75%]">
                <div className={cn(
                  'px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed',
                  isSent 
                    ? 'bg-primary text-primary-foreground rounded-br-md' 
                    : 'bg-card border border-border rounded-bl-md'
                )}>
                  {msg.content}
                </div>
                {showTime && (
                  <div className={cn('flex items-center gap-1.5 mt-1', isSent ? 'justify-end' : 'justify-start')}>
                    <p className="text-[10px] text-muted-foreground">{formatTime(msg.timestamp)}</p>
                    {isSent && <MessageStatusIndicator status={msg.status} />}
                  </div>
                )}
              </div>
            </div>
          )
        })
        )}
        {isTyping && <ChatTypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="sticky bottom-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
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
    </div>
  )
}
