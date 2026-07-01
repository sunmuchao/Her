'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
import { WechatIcon } from '@/components/her/ui/wechat-icon'
import { cn } from '@/lib/utils'

interface WelcomePageProps {
  maskedPhoneNumber?: string
  onOneClickLogin: () => void | Promise<void>
  onWeChatLogin: () => void | Promise<void>
  onPhoneLogin: () => void
  onAccountRecovery?: () => void
}

export default function WelcomePage({
  maskedPhoneNumber = '138****8000',
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
        {/* Logo and branding area */}
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

        {/* Login section */}
        <div
          className={cn(
            'pb-6 space-y-4 transition-all duration-700 ease-out delay-500',
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

          {/* Phone number display with change option */}
          <div className="flex items-center justify-center gap-2 mb-2">
            <span className="text-sm text-muted-foreground">本机号码</span>
            <span className="text-base font-medium text-foreground tracking-wider">
              {maskedPhoneNumber}
            </span>
            <button
              onClick={onPhoneLogin}
              className="text-sm text-primary hover:text-primary/80 transition-colors"
              aria-label="使用其他手机号"
            >
              换号
            </button>
          </div>

          {/* One-click login button - primary action */}
          <button
            onClick={handleOneClickLogin}
            disabled={isLoading !== null}
            className={cn(
              'w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium transition-all',
              'active:scale-[0.98] disabled:opacity-70',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
            )}
            aria-label="一键登录"
          >
            {isLoading === 'oneclick' ? (
              <div className="flex items-center justify-center gap-3">
                <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                <span>正在验证...</span>
              </div>
            ) : (
              '一键登录'
            )}
          </button>

          {/* WeChat login - secondary action */}
          <button
            onClick={handleWeChatLogin}
            disabled={isLoading !== null}
            className="w-full py-3 flex items-center justify-center gap-2 text-sm font-medium text-muted-foreground"
          >
            {isLoading === 'wechat' ? (
              <div className="w-4 h-4 border-2 border-muted-foreground/30 border-t-muted-foreground rounded-full animate-spin" />
            ) : (
              <WechatIcon size={16} />
            )}
            使用微信登录
          </button>

          {/* Account recovery link */}
          {onAccountRecovery && (
            <button
              onClick={onAccountRecovery}
              disabled={isLoading !== null}
              className="w-full text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              无法登录？找回账号
            </button>
          )}
        </div>

        {/* Footer - consistent with other pages */}
        <div
          className={cn(
            'pb-8 safe-area-bottom transition-all duration-700 ease-out delay-700',
            mounted ? 'opacity-100' : 'opacity-0',
          )}
        >
          <p className="text-center text-xs text-muted-foreground leading-relaxed">
            登录即表示同意
            <Link href="/legal/terms" className="underline underline-offset-2 mx-1">
              用户协议
            </Link>
            和
            <Link href="/legal/privacy" className="underline underline-offset-2 mx-1">
              隐私政策
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
