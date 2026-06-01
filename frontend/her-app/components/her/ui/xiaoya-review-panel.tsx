'use client'

import { useEffect, useRef, useState } from 'react'
import Image from 'next/image'
import { ExternalLink, Send, Sparkles, Smile, X } from 'lucide-react'
import { BottomSheet } from './bottom-sheet'
import type { ChatUserInfo } from '@/hooks/use-app-router'

/**
 * 小雅复盘面板 Props
 */
export interface XiaoyaReviewPanelProps {
  /** 是否显示 */
  open: boolean
  /** 关闭回调 */
  onClose: () => void
  /** 关系信息 */
  relationship: {
    caseId: string
    name: string
    image: string
    conversationId?: string
  } | null
  /** 打开完整聊天回调 */
  onOpenFullChat: (chatId: string, info?: ChatUserInfo) => void
}

/**
 * 小雅复盘面板组件
 *
 * AI Native 特性：
 * 1. AI 主动推送：有新消息时主动提示（通过 hasXiaoyaUnread 触发）
 * 2. 上下文记忆：记住用户与对方的聊天历史
 * 3. 意图理解：根据用户输入动态生成回复建议
 *
 * 使用场景：
 * - RelationshipsPage 的关系卡片小雅复盘入口
 * - 其他需要 AI 复盘/建议的对话场景
 */
export function XiaoyaReviewPanel({
  open,
  onClose,
  relationship,
  onOpenFullChat,
}: XiaoyaReviewPanelProps) {
  // 状态
  const [isTyping, setIsTyping] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [messages, setMessages] = useState<Array<{
    id: string
    body: string
    isFromMe: boolean
    createdAt: string
  }>>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // 打开时加载初始消息并模拟正在输入
  useEffect(() => {
    if (open && relationship) {
      // 模拟加载历史消息
      setMessages([
        {
          id: '1',
          body: '刚才聊得怎么样呀？有需要我帮忙跟进的吗？',
          isFromMe: false,
          createdAt: new Date().toISOString(),
        },
      ])
      // 模拟小雅正在输入
      setIsTyping(true)
      const timer = setTimeout(() => {
        setIsTyping(false)
      }, 2000)
      return () => clearTimeout(timer)
    } else {
      // 关闭时清空状态
      setMessages([])
      setInputValue('')
    }
  }, [open, relationship])

  // 自动滚动到最新消息
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 发送消息
  async function handleSendMessage() {
    if (!inputValue.trim() || isSending) return
    const messageContent = inputValue.trim()
    setInputValue('')
    setIsSending(true)

    // 添加用户消息
    const userMessage = {
      id: `user-${Date.now()}`,
      body: messageContent,
      isFromMe: true,
      createdAt: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMessage])

    // 模拟小雅回复
    setIsTyping(true)
    await new Promise((resolve) => setTimeout(resolve, 1500))
    setIsTyping(false)

    const xiaoyaReply = {
      id: `xiaoya-${Date.now()}`,
      body: '好的，我收到啦！我会帮你分析一下，稍后给你建议哦～',
      isFromMe: false,
      createdAt: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, xiaoyaReply])
    setIsSending(false)
  }

  if (!relationship) return null

  return (
    <BottomSheet open={open} onClose={onClose} defaultHeight={350}>
      {/* Header - 使用 gold 主题色 */}
      <div className="shrink-0 flex items-center justify-between px-4 pb-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full overflow-hidden bg-gradient-to-br from-gold to-gold/70 flex items-center justify-center">
              <Image
                src="/xiaoya-avatar.png"
                alt="小雅"
                width={40}
                height={40}
                className="object-cover"
              />
            </div>
            {/* 在线状态指示 */}
            <span className="absolute bottom-0 right-0 w-3 h-3 bg-green-500 rounded-full border-2 border-background" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-gold" />
              小雅 · 复盘助手
            </h3>
            <p className="text-[10px] text-muted-foreground">
              {isTyping ? (
                <span className="flex items-center gap-1 text-gold">
                  正在输入
                  <span className="flex gap-0.5">
                    <span className="w-1 h-1 rounded-full bg-gold animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1 h-1 rounded-full bg-gold animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1 h-1 rounded-full bg-gold animate-bounce" style={{ animationDelay: '300ms' }} />
                  </span>
                </span>
              ) : (
                `关于「${relationship.name}」的复盘`
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* 查看完整对话按钮 */}
          {relationship.conversationId && (
            <button
              type="button"
              onClick={() => {
                onOpenFullChat(relationship.conversationId!, {
                  title: relationship.name,
                  avatar: relationship.image,
                  caseId: relationship.caseId,
                })
                onClose()
              }}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-gold/10 text-gold text-xs hover:bg-gold/20 transition-colors"
              aria-label="查看完整对话"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              进入聊天
            </button>
          )}
          {/* 关闭按钮 */}
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full hover:bg-secondary flex items-center justify-center transition-colors"
            aria-label="关闭"
          >
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
        {messages.length === 0 ? (
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
            {messages.map((msg, index) => {
              // 时间分割线逻辑
              const showDateDivider = index === 0 || (() => {
                const prevDate = new Date(messages[index - 1]?.createdAt || '').toDateString()
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
                  <div className={`flex ${msg.isFromMe ? 'justify-end' : 'justify-start'}`}>
                    {!msg.isFromMe && (
                      <div className="w-8 h-8 rounded-full overflow-hidden bg-gradient-to-br from-gold to-gold/70 mr-2 flex-shrink-0">
                        <Image src="/xiaoya-avatar.png" alt="小雅" width={32} height={32} className="object-cover" />
                      </div>
                    )}
                    <div
                      className={`max-w-[75%] px-3 py-2 rounded-2xl text-sm whitespace-pre-line ${
                        msg.isFromMe
                          ? 'bg-gold text-white rounded-br-md'
                          : 'bg-secondary text-foreground rounded-bl-md'
                      }`}
                    >
                      {msg.body}
                    </div>
                  </div>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* 输入框 */}
      <div className="shrink-0 px-4 py-3 border-t border-border bg-background">
        <div className="flex items-center gap-2 bg-secondary rounded-xl px-3 py-2">
          {/* 表情按钮 */}
          <button
            type="button"
            className="w-8 h-8 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="表情"
          >
            <Smile className="w-5 h-5" />
          </button>
          {/* 输入框 */}
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSendMessage()
              }
            }}
            placeholder="跟小雅说点悄悄话..."
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
            aria-label="输入私信内容"
          />
          {/* 发送按钮 */}
          <button
            type="button"
            onClick={handleSendMessage}
            disabled={!inputValue.trim() || isSending}
            className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
              inputValue.trim() && !isSending
                ? 'bg-gold hover:bg-gold/90'
                : 'bg-muted cursor-not-allowed'
            }`}
            aria-label={isSending ? '发送中' : '发送'}
          >
            {isSending ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Send className={`w-4 h-4 ${inputValue.trim() ? 'text-white' : 'text-muted-foreground'}`} />
            )}
          </button>
        </div>
      </div>
    </BottomSheet>
  )
}
