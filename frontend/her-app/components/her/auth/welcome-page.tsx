'use client'

import { useState, useEffect } from 'react'
import { Smartphone, ChevronRight } from 'lucide-react'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
import { WechatIcon } from '@/components/her/ui/wechat-icon'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface WelcomePageProps {
  onOneClickLogin: () => void | Promise<void>
  onWeChatLogin: () => void | Promise<void>
  onPhoneLogin: () => void
  onAccountRecovery?: () => void
}

export default function WelcomePage({
  onOneClickLogin,
  onWeChatLogin,
  onPhoneLogin,
  onAccountRecovery,
}: WelcomePageProps) {
  const [isLoading, setIsLoading] = useState<'oneclick' | 'wechat' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 100)
    return () => clearTimeout(timer)
  }, [])

  const handleOneClickLogin = async () => {
    setIsLoading('oneclick')
    setError(null)
    try {
      await onOneClickLogin()
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后重试')
    } finally {
      setIsLoading(null)
    }
  }

  const handleWeChatLogin = async () => {
    setIsLoading('wechat')
    setError(null)
    try {
      await onWeChatLogin()
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后重试')
    } finally {
      setIsLoading(null)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto">
      <div className="flex-1 flex flex-col px-8 pt-safe-area-top">
        <div className="flex-1 flex flex-col justify-center items-center pt-16 pb-8">
          <div
            className={cn(
              'mb-10 transition-all duration-700 ease-out',
              mounted
                ? 'opacity-100 translate-y-0 scale-100'
                : 'opacity-0 translate-y-4 scale-95',
            )}
          >
            <div className="relative">
              <div className="absolute inset-0 bg-gradient-to-br from-rose-soft to-gold-soft rounded-full blur-xl opacity-60 scale-110" />
              <div className="relative rounded-full shadow-lg">
                <XiaoyaAvatar size={112} priority />
              </div>
            </div>
          </div>

          <h1
            className={cn(
              'font-serif text-5xl text-foreground mb-4 transition-all duration-700 ease-out delay-150',
              mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4',
            )}
          >
            小雅
          </h1>

          <p
            className={cn(
              'text-center text-lg text-muted-foreground font-light leading-relaxed max-w-[280px] transition-all duration-700 ease-out delay-300',
              mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4',
            )}
          >
            认真关系，从认真了解开始
          </p>
        </div>

        <div
          className={cn(
            'pb-10 space-y-3 transition-all duration-700 ease-out delay-500',
            mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6',
          )}
        >
          {error && (
            <div
              className="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive animate-fade-in-up"
              role="alert"
            >
              {error}
            </div>
          )}

          <button
            onClick={handleOneClickLogin}
            disabled={isLoading !== null}
            className={cn(
              'w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium transition-all',
              'active:scale-[0.98] disabled:opacity-70',
              'hover:shadow-lg hover:shadow-primary/20',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
            )}
            aria-label="使用本机号码一键登录"
          >
            <span className="flex items-center justify-center gap-3">
              {isLoading === 'oneclick' ? (
                <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
              ) : (
                <>
                  <Smartphone className="w-5 h-5" aria-hidden="true" />
                  本机号码一键登录
                </>
              )}
            </span>
          </button>

          <button
            onClick={handleWeChatLogin}
            disabled={isLoading !== null}
            className={cn(
              'w-full py-4 bg-card rounded-2xl border border-border text-foreground font-medium transition-all',
              'active:scale-[0.98] disabled:opacity-70',
              'hover:bg-secondary hover:border-secondary',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
            )}
            aria-label="使用微信登录"
          >
            <span className="flex items-center justify-center gap-3">
              {isLoading === 'wechat' ? (
                <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              ) : (
                <>
                  <WechatIcon size={20} />
                  微信登录
                </>
              )}
            </span>
          </button>

          <Button
            variant="link"
            onClick={onPhoneLogin}
            disabled={isLoading !== null}
            className="w-full text-sm"
            aria-label="使用手机号登录"
          >
            手机号登录
            <ChevronRight className="w-4 h-4" aria-hidden="true" />
          </Button>
          {onAccountRecovery && (
            <Button
              variant="ghost"
              onClick={onAccountRecovery}
              disabled={isLoading !== null}
              className="w-full text-sm text-muted-foreground"
            >
              无法登录？找回账号
            </Button>
          )}
        </div>

        <div
          className={cn(
            'pb-8 safe-area-bottom transition-all duration-700 ease-out delay-700',
            mounted ? 'opacity-100' : 'opacity-0',
          )}
        >
          <p className="text-center text-xs text-muted-foreground leading-relaxed">
            登录即表示同意
            <button
              className="underline underline-offset-2 mx-1 hover:text-foreground transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded"
              aria-label="查看用户协议"
            >
              用户协议
            </button>
            和
            <button
              className="underline underline-offset-2 mx-1 hover:text-foreground transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded"
              aria-label="查看隐私政策"
            >
              隐私政策
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
