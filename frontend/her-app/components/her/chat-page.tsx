'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Phone, MoreVertical, Send, Image as ImageIcon, BadgeCheck, Mic } from 'lucide-react'
import Image from 'next/image'
import { ChatTypingIndicator } from './ui/typing-indicator'
import { gatewayJson, queryString } from '@/lib/gateway'

interface ChatPageProps {
  chatId: string | null
  onBack: () => void
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

const fallbackMessages = [
  { id: '1', type: 'received' as const, content: '你好呀，很高兴认识你～', timestamp: '10:30' },
  { id: '2', type: 'sent' as const, content: '你好！很高兴认识你。', timestamp: '10:32' },
]

export default function ChatPage({ chatId, onBack }: ChatPageProps) {
  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [messages, setMessages] = useState(fallbackMessages)
  const [chatTitle, setChatTitle] = useState('聊天')
  const [verified, setVerified] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chatId) return
    const requesterId = process.env.NEXT_PUBLIC_HER_USER_ID
    if (!requesterId) return

    let cancelled = false
    async function loadConversation() {
      try {
        const [conversationData, messageData] = await Promise.all([
          gatewayJson<ConversationResponse>(
            `/v2/chat/conversations/${chatId}${queryString({ requester_id: requesterId })}`,
          ),
          gatewayJson<MessagesResponse>(
            `/v2/chat/conversations/${chatId}/messages${queryString({ requester_id: requesterId })}`,
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
          messageData.messages.map((message) => ({
            id: String(message.message_id),
            type: message.author_id === requesterId ? ('sent' as const) : ('received' as const),
            content: message.body,
            timestamp: message.created_at,
          })),
        )
      } catch {
        // Fall back to demo conversation when backend chat is unavailable for this entry.
      }
    }

    void loadConversation()
    return () => {
      cancelled = true
    }
  }, [chatId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [isTyping, messages])

  const handleSend = async () => {
    const body = inputValue.trim()
    if (!body || !chatId) return
    const authorId = process.env.NEXT_PUBLIC_HER_USER_ID
    if (!authorId) return
    setInputValue('')

    try {
      await gatewayJson(`/v2/chat/conversations/${chatId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          author_id: authorId,
          body,
        }),
      })
      const messageData = await gatewayJson<MessagesResponse>(
        `/v2/chat/conversations/${chatId}/messages${queryString({ requester_id: authorId })}`,
      )
      setMessages(
        messageData.messages.map((message) => ({
          id: String(message.message_id),
          type: message.author_id === authorId ? ('sent' as const) : ('received' as const),
          content: message.body,
          timestamp: message.created_at,
        })),
      )
      setIsTyping(true)
      setTimeout(() => setIsTyping(false), 1200)
    } catch {
      setMessages((prev) => [...prev, { id: `${Date.now()}`, type: 'sent', content: body, timestamp: '刚刚' }])
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button onClick={onBack} className="w-8 h-8 flex items-center justify-center">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="w-8 h-8 rounded-full overflow-hidden bg-secondary flex items-center justify-center">
            <Image
              src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face"
              alt={chatTitle}
              width={32}
              height={32}
              className="object-cover"
            />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-sm">{chatTitle}</span>
              {verified && <BadgeCheck className="w-4 h-4 text-primary" />}
            </div>
          </div>
          <button className="w-8 h-8 flex items-center justify-center">
            <Phone className="w-5 h-5 text-muted-foreground" />
          </button>
          <button className="w-8 h-8 flex items-center justify-center">
            <MoreVertical className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => {
          const isSent = msg.type === 'sent'
          return (
            <div key={msg.id} className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}>
              <div className="max-w-[75%]">
                <div className={`px-3.5 py-2.5 rounded-2xl text-sm ${
                  isSent ? 'bg-primary text-primary-foreground rounded-br-md' : 'bg-card border border-border rounded-bl-md'
                }`}>
                  {msg.content}
                </div>
                <p className={`text-[10px] text-muted-foreground mt-1 ${isSent ? 'text-right' : ''}`}>{msg.timestamp}</p>
              </div>
            </div>
          )
        })}
        {isTyping && <ChatTypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      <div className="sticky bottom-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
          <button aria-label="发送图片" className="w-8 h-8 flex items-center justify-center text-muted-foreground">
            <ImageIcon className="w-5 h-5" />
          </button>
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="输入消息..."
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
          />
          <button aria-label="语音输入" className="w-8 h-8 flex items-center justify-center text-muted-foreground">
            <Mic className="w-5 h-5" />
          </button>
          <button
            aria-label="发送消息"
            onClick={handleSend}
            className={`w-8 h-8 rounded-full flex items-center justify-center ${inputValue.trim() ? 'bg-primary' : 'bg-muted'}`}
          >
            <Send className={`w-4 h-4 ${inputValue.trim() ? 'text-primary-foreground' : 'text-muted-foreground'}`} />
          </button>
        </div>
      </div>
    </div>
  )
}
