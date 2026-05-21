'use client'

import { useState, useEffect } from 'react'
import { Apple, MessageCircle } from 'lucide-react'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'
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
  const [agreedToTerms, setAgreedToTerms] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 100)
    return () => clearTimeout(timer)
  }, [])

  const handleOneClickLogin = async () => {
    if (!agreedToTerms) {
      setError('请先同意用户协议和隐私政策')
      return
    }
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
    if (!agreedToTerms) {
      setError('请先同意用户协议和隐私政策')
      return
    }
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

        {/* Login section - Soul style integrated */}
        <div
          className={cn(
            'pb-6 transition-all duration-700 ease-out delay-500',
            mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6',
          )}
        >
          {error && (
            <div
              className="rounded-2xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive animate-fade-in-up mb-4"
              role="alert"
            >
              {error}
            </div>
          )}

          {/* Phone number display with change option */}
          <div className="flex items-center justify-center gap-2 mb-4">
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
              'w-full py-4 bg-foreground rounded-full text-background font-medium transition-all',
              'active:scale-[0.98] disabled:opacity-70',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2',
            )}
            aria-label="一键登录"
          >
            {isLoading === 'oneclick' ? (
              <div className="flex items-center justify-center gap-3">
                <div className="w-5 h-5 border-2 border-background/30 border-t-background rounded-full animate-spin" />
                <span>正在验证...</span>
              </div>
            ) : (
              '一键登录'
            )}
          </button>

          {/* Alternative login methods - de-emphasized icons */}
          <div className="flex items-center justify-center gap-6 mt-6">
            <button
              onClick={handleWeChatLogin}
              disabled={isLoading !== null}
              className={cn(
                'w-12 h-12 rounded-full border border-border/50 flex items-center justify-center transition-all',
                'hover:bg-secondary/50 active:scale-95 disabled:opacity-50',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              )}
              aria-label="微信登录"
            >
              {isLoading === 'wechat' ? (
                <div className="w-5 h-5 border-2 border-muted-foreground/30 border-t-muted-foreground rounded-full animate-spin" />
              ) : (
                <MessageCircle className="w-6 h-6 text-muted-foreground" />
              )}
            </button>
            <button
              disabled={isLoading !== null}
              className={cn(
                'w-12 h-12 rounded-full border border-border/50 flex items-center justify-center transition-all',
                'hover:bg-secondary/50 active:scale-95 disabled:opacity-50',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
              )}
              aria-label="Apple登录"
            >
              <Apple className="w-6 h-6 text-muted-foreground" />
            </button>
          </div>

          {/* Account recovery link */}
          {onAccountRecovery && (
            <button
              onClick={onAccountRecovery}
              disabled={isLoading !== null}
              className="w-full mt-4 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              无法登录？找回账号
            </button>
          )}
        </div>

        {/* Terms agreement - Soul style with checkbox */}
        <div
          className={cn(
            'pb-8 safe-area-bottom transition-all duration-700 ease-out delay-700',
            mounted ? 'opacity-100' : 'opacity-0',
          )}
        >
          <label className="flex items-start justify-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              className="mt-0.5 w-4 h-4 rounded border-border text-primary focus:ring-primary focus:ring-offset-0"
            />
            <span className="text-xs text-muted-foreground leading-relaxed">
              登录注册即表示同意
              <button
                className="underline underline-offset-2 mx-0.5 hover:text-foreground transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded"
                aria-label="查看用户协议"
              >
                用户协议
              </button>
              、
              <button
                className="underline underline-offset-2 mx-0.5 hover:text-foreground transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-primary rounded"
                aria-label="查看隐私政策"
              >
                隐私政策
              </button>
              及移动统一认证服务条款
            </span>
          </label>
        </div>
      </div>
    </div>
  )
}
