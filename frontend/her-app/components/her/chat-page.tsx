'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, Loader2, Send } from 'lucide-react'

import { gatewayJson, queryString } from '@/lib/gateway'
import type { HerRuntimeContext } from '@/lib/runtime-context'

interface ChatPageProps {
  conversationId: string
  runtimeContext: HerRuntimeContext
  onBack: () => void
}

type ConversationPayload = {
  conversation: {
    conversation_id: string
    display_name?: string
    layout_role?: string
  }
}

type MessagesPayload = {
  messages: Array<{
    message_id: number
    body?: string
    author_id?: string
    created_at?: string
  }>
}

export default function ChatPage({
  conversationId,
  runtimeContext,
  onBack,
}: ChatPageProps) {
  const [title, setTitle] = useState('当前会话')
  const [messages, setMessages] = useState<MessagesPayload['messages']>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [inputValue, setInputValue] = useState('')

  useEffect(() => {
    let active = true

    async function loadConversation() {
      if (!runtimeContext.userId) {
        setLoading(false)
        setError('缺少 user_id，当前无法读取会话。')
        return
      }
      setLoading(true)
      setError(null)
      try {
        const [conversation, payload] = await Promise.all([
          gatewayJson<ConversationPayload>(
            `/v2/chat/conversations/${conversationId}${queryString({
              requester_id: runtimeContext.userId,
            })}`,
          ),
          gatewayJson<MessagesPayload>(
            `/v2/chat/conversations/${conversationId}/messages${queryString({
              requester_id: runtimeContext.userId,
              limit: 50,
            })}`,
          ),
        ])
        if (!active) {
          return
        }
        setTitle(
          conversation.conversation.display_name ||
            conversation.conversation.layout_role ||
            '当前会话',
        )
        setMessages(payload.messages || [])
      } catch (err) {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : '会话加载失败')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadConversation()
    return () => {
      active = false
    }
  }, [conversationId, runtimeContext.userId])

  async function sendMessage() {
    if (!runtimeContext.userId || !inputValue.trim()) {
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await gatewayJson(`/v2/chat/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          requester_id: runtimeContext.userId,
          author_id: runtimeContext.userId,
          body: inputValue.trim(),
        }),
      })
      const payload = await gatewayJson<MessagesPayload>(
        `/v2/chat/conversations/${conversationId}/messages${queryString({
          requester_id: runtimeContext.userId,
          limit: 50,
        })}`,
      )
      setMessages(payload.messages || [])
      setInputValue('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
      <header className="sticky top-0 z-20 safe-area-top">
        <div className="glass-soft border-b border-border/30">
          <div className="px-4 py-3 flex items-center gap-3">
            <button
              onClick={onBack}
              className="w-10 h-10 rounded-full hover:bg-secondary/60 flex items-center justify-center transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-foreground" />
            </button>
            <div>
              <h1 className="font-medium text-foreground">{title}</h1>
              <p className="text-xs text-muted-foreground">已接入真实 conversation messages</p>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 bg-gradient-to-b from-background to-blush/20">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            正在加载聊天记录
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : (
          messages.map((message) => {
            const isSelf = String(message.author_id || '') === String(runtimeContext.userId || '')
            return (
              <div
                key={message.message_id}
                className={`flex ${isSelf ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-3xl px-4 py-3 shadow-soft ${
                    isSelf
                      ? 'bg-gradient-to-br from-primary to-rose text-primary-foreground rounded-br-lg'
                      : 'bg-card border border-border/30 text-foreground rounded-bl-lg'
                  }`}
                >
                  <p className="text-sm leading-6 whitespace-pre-wrap">{message.body}</p>
                  {message.created_at ? (
                    <span className="mt-1 block text-[10px] opacity-70">{message.created_at}</span>
                  ) : null}
                </div>
              </div>
            )
          })
        )}
      </div>

      <div className="border-t border-border/30 bg-background/90 px-5 pb-6 pt-4 backdrop-blur-xl safe-area-bottom">
        <div className="flex items-end gap-3">
          <div className="flex-1 rounded-3xl border border-border/40 bg-card px-4 py-3 shadow-soft">
            <textarea
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              rows={1}
              placeholder="给对方发一条消息"
              className="w-full resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
          </div>
          <button
            disabled={submitting || !inputValue.trim()}
            onClick={sendMessage}
            className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-r from-primary to-rose text-primary-foreground shadow-elevated disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
      </div>
    </div>
  )
}
