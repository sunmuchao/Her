'use client'

import { useState } from 'react'
import { ArrowLeft, Phone, MoreVertical, Send, Image as ImageIcon, Smile, BadgeCheck, Info } from 'lucide-react'
import Image from 'next/image'

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
    online: true,
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
    online: false,
  },
]

const chatMessages = [
  {
    id: '1',
    type: 'system' as const,
    content: '你们已匹配成功，可以开始聊天了',
    timestamp: '2024年3月10日',
  },
  {
    id: '2',
    type: 'received' as const,
    content: '你好呀，很高兴认识你～',
    timestamp: '10:30',
  },
  {
    id: '3',
    type: 'sent' as const,
    content: '你好！我看了你的资料，感觉我们有很多共同点',
    timestamp: '10:32',
  },
  {
    id: '4',
    type: 'received' as const,
    content: '是呀，我也觉得～你也喜欢看展吗？',
    timestamp: '10:35',
  },
  {
    id: '5',
    type: 'sent' as const,
    content: '对的，最近正好想去看龙美术馆的新展，你有兴趣吗？',
    timestamp: '10:38',
  },
  {
    id: '6',
    type: 'received' as const,
    content: '哇，那个展我也一直想去！听说布展很用心',
    timestamp: '10:40',
  },
  {
    id: '7',
    type: 'sent' as const,
    content: '那不如周末一起去？',
    timestamp: '10:42',
  },
  {
    id: '8',
    type: 'received' as const,
    content: '好的，那我们周六见面聊聊吧',
    timestamp: '10:45',
  },
]

const currentChatUser = {
  name: '林悦',
  age: 28,
  image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200&h=200&fit=crop&crop=face',
  verified: true,
  stage: '初步了解',
  matchDays: 3,
}

export default function ChatPage({ chatId, onBack }: ChatPageProps) {
  const [inputValue, setInputValue] = useState('')
  const [selectedChat, setSelectedChat] = useState(chatId || chatList[0]?.id)

  // If no chatId, show chat list
  if (!chatId) {
    return (
      <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
        {/* Header */}
        <header className="sticky top-0 z-20 safe-area-top">
          <div className="glass-soft border-b border-border/30">
            <div className="px-5 py-4 flex items-center gap-3">
              <button
                onClick={onBack}
                className="w-10 h-10 rounded-full bg-secondary/60 flex items-center justify-center hover:bg-secondary transition-colors"
              >
                <ArrowLeft className="w-5 h-5 text-foreground" />
              </button>
              <div>
                <h1 className="font-medium text-foreground">消息</h1>
                <p className="text-xs text-muted-foreground">{chatList.length}个对话</p>
              </div>
            </div>
          </div>
        </header>

        {/* Chat list */}
        <div className="flex-1 overflow-y-auto">
          {chatList.map((chat) => (
            <button
              key={chat.id}
              onClick={() => setSelectedChat(chat.id)}
              className="w-full px-5 py-4 flex items-center gap-3 border-b border-border/30 hover:bg-secondary/30 transition-colors text-left"
            >
              <div className="relative">
                <div className="w-14 h-14 rounded-full overflow-hidden border-2 border-rose-soft">
                  <Image
                    src={chat.image}
                    alt={chat.name}
                    width={56}
                    height={56}
                    className="object-cover"
                  />
                </div>
                {chat.online && (
                  <div className="absolute bottom-0 right-0 w-4 h-4 bg-green-500 rounded-full border-2 border-background" />
                )}
                {chat.unread > 0 && (
                  <div className="absolute -top-1 -right-1 w-5 h-5 bg-primary rounded-full flex items-center justify-center">
                    <span className="text-[10px] font-medium text-primary-foreground">{chat.unread}</span>
                  </div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-medium text-foreground">{chat.name}</h3>
                  {chat.verified && <BadgeCheck className="w-4 h-4 text-primary shrink-0" />}
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

  // Individual chat view
  return (
    <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={onBack}
              className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            
            <div className="flex items-center gap-3 flex-1">
              <div className="relative">
                <div className="w-10 h-10 rounded-full overflow-hidden border border-rose-soft">
                  <Image
                    src={currentChatUser.image}
                    alt={currentChatUser.name}
                    width={40}
                    height={40}
                    className="object-cover"
                  />
                </div>
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <h2 className="font-medium text-foreground text-sm">{currentChatUser.name}</h2>
                  {currentChatUser.verified && <BadgeCheck className="w-4 h-4 text-primary" />}
                </div>
                <span className="text-[10px] text-muted-foreground">{currentChatUser.stage} · 已匹配{currentChatUser.matchDays}天</span>
              </div>
            </div>

            <button className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors">
              <Phone className="w-5 h-5 text-muted-foreground" />
            </button>
            <button className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors">
              <MoreVertical className="w-5 h-5 text-muted-foreground" />
            </button>
          </div>
        </div>
      </header>

      {/* Relationship hint banner */}
      <div className="px-4 py-2 bg-blush/40 border-b border-rose-soft/30">
        <div className="flex items-center gap-2 text-xs text-taupe">
          <Info className="w-4 h-4" />
          <span>保持真诚沟通，建立美好关系</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {chatMessages.map((message) => {
          if (message.type === 'system') {
            return (
              <div key={message.id} className="flex justify-center">
                <span className="text-[10px] text-muted-foreground bg-secondary/60 px-3 py-1 rounded-full">
                  {message.content}
                </span>
              </div>
            )
          }

          const isSent = message.type === 'sent'
          
          return (
            <div key={message.id} className={`flex ${isSent ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[75%] ${isSent ? 'order-1' : ''}`}>
                <div
                  className={`px-4 py-3 ${
                    isSent
                      ? 'bg-primary text-primary-foreground rounded-3xl rounded-br-lg'
                      : 'bg-card text-card-foreground rounded-3xl rounded-bl-lg shadow-soft border border-border/50'
                  }`}
                >
                  <p className="text-sm leading-relaxed">{message.content}</p>
                </div>
                <span className={`text-[10px] text-muted-foreground mt-1 block ${isSent ? 'text-right' : ''}`}>
                  {message.timestamp}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Input area */}
      <div className="sticky bottom-0 px-4 py-3 safe-area-bottom">
        <div className="glass-soft rounded-2xl border border-border/50 shadow-soft">
          <div className="flex items-end gap-2 p-2">
            <button className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors shrink-0">
              <ImageIcon className="w-5 h-5 text-muted-foreground" />
            </button>
            <div className="flex-1 min-h-[40px] max-h-32">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="输入消息..."
                rows={1}
                className="w-full px-3 py-2.5 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none resize-none leading-relaxed"
              />
            </div>
            <button className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors shrink-0">
              <Smile className="w-5 h-5 text-muted-foreground" />
            </button>
            <button className="w-10 h-10 rounded-full bg-primary flex items-center justify-center shadow-soft transition-all hover:bg-rose active:scale-95 shrink-0">
              <Send className="w-4 h-4 text-primary-foreground" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
