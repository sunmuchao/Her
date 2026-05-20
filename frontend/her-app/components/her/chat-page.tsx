'use client'

import { useState, useEffect, useRef } from 'react'
import { ArrowLeft, Phone, MoreVertical, Send, Image as ImageIcon, BadgeCheck, Mic } from 'lucide-react'
import Image from 'next/image'
import { ChatTypingIndicator } from './ui/typing-indicator'

interface ChatPageProps {
  chatId: string | null
  onBack: () => void
}

const chatList = [
  {
    id: '1',
    name: '林悦',
    age: 28,
    image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
    lastMessage: '好的，那我们周六见面聊聊吧',
    lastMessageTime: '刚刚',
    unread: 2,
    verified: true,
  },
  {
    id: '2',
    name: '陈思',
    age: 27,
    image: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=200&h=200&fit=crop&crop=face',
    lastMessage: '那家咖啡店的环境真的很不错',
    lastMessageTime: '2小时前',
    unread: 0,
    verified: true,
  },
]

const chatMessages = [
  { id: '1', type: 'system' as const, content: '你们已匹配成功', timestamp: '3月10日' },
  { id: '2', type: 'received' as const, content: '你好呀，很高兴认识你～', timestamp: '10:30' },
  { id: '3', type: 'sent' as const, content: '你好！我看了你的资料，感觉我们有很多共同点', timestamp: '10:32' },
  { id: '4', type: 'received' as const, content: '是呀，我也觉得～你也喜欢看展吗？', timestamp: '10:35' },
  { id: '5', type: 'sent' as const, content: '对的，最近正好想去看龙美术馆的新展', timestamp: '10:38' },
  { id: '6', type: 'received' as const, content: '哇，那个展我也一直想去！', timestamp: '10:40' },
  { id: '7', type: 'sent' as const, content: '那不如周末一起去？', timestamp: '10:42' },
  { id: '8', type: 'received' as const, content: '好的，那我们周六见面聊聊吧', timestamp: '10:45' },
]

const currentChatUser = {
  name: '林悦',
  image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
  verified: true,
}

export default function ChatPage({ chatId, onBack }: ChatPageProps) {
  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chatId) {
      const timer = setTimeout(() => {
        setIsTyping(true)
        setTimeout(() => setIsTyping(false), 2000)
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [chatId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [isTyping])

  // Chat list view
  if (!chatId) {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
          <div className="px-4 py-3 flex items-center gap-3">
            <button onClick={onBack} className="w-8 h-8 flex items-center justify-center">
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="font-medium">消息</h1>
          </div>
        </header>

        <div className="flex-1">
          {chatList.map((chat) => (
            <button
              key={chat.id}
              className="w-full px-4 py-3 flex items-center gap-3 border-b border-border hover:bg-secondary/50 transition-colors text-left"
            >
              <div className="relative">
                <div className="w-12 h-12 rounded-full overflow-hidden">
                  <Image src={chat.image} alt={chat.name} width={48} height={48} className="object-cover" />
                </div>
                {chat.unread > 0 && (
                  <span className="absolute -top-1 -right-1 w-5 h-5 bg-rose text-[10px] font-medium text-white rounded-full flex items-center justify-center">
                    {chat.unread}
                  </span>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="font-medium">{chat.name}</span>
                  {chat.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
                  <span className="ml-auto text-[10px] text-muted-foreground">{chat.lastMessageTime}</span>
                </div>
                <p className="text-sm text-muted-foreground truncate">{chat.lastMessage}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    )
  }

  // Chat detail view
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button onClick={onBack} className="w-8 h-8 flex items-center justify-center">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="w-8 h-8 rounded-full overflow-hidden">
            <Image src={currentChatUser.image} alt={currentChatUser.name} width={32} height={32} className="object-cover" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-sm">{currentChatUser.name}</span>
              {currentChatUser.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
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

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {chatMessages.map((msg) => {
          if (msg.type === 'system') {
            return (
              <div key={msg.id} className="flex justify-center">
                <span className="text-[10px] text-muted-foreground bg-secondary px-2 py-1 rounded-full">{msg.content}</span>
              </div>
            )
          }
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

      {/* Input */}
      <div className="sticky bottom-0 px-4 py-3 bg-background border-t border-border safe-area-bottom">
        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
          <button className="w-8 h-8 flex items-center justify-center text-muted-foreground">
            <ImageIcon className="w-5 h-5" />
          </button>
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="输入消息..."
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
          />
          <button className="w-8 h-8 flex items-center justify-center text-muted-foreground">
            <Mic className="w-5 h-5" />
          </button>
          <button className={`w-8 h-8 rounded-full flex items-center justify-center ${inputValue.trim() ? 'bg-primary' : 'bg-muted'}`}>
            <Send className={`w-4 h-4 ${inputValue.trim() ? 'text-primary-foreground' : 'text-muted-foreground'}`} />
          </button>
        </div>
      </div>
    </div>
  )
}
