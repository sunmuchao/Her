'use client'

import { useState } from 'react'
import { Smartphone, MessageCircle, ChevronRight } from 'lucide-react'

interface WelcomePageProps {
  onOneClickLogin: () => void
  onWeChatLogin: () => void
  onPhoneLogin: () => void
}

export default function WelcomePage({ 
  onOneClickLogin, 
  onWeChatLogin, 
  onPhoneLogin 
}: WelcomePageProps) {
  const [isLoading, setIsLoading] = useState<'oneclick' | 'wechat' | null>(null)

  const handleOneClickLogin = () => {
    setIsLoading('oneclick')
    setTimeout(() => {
      setIsLoading(null)
      onOneClickLogin()
    }, 800)
  }

  const handleWeChatLogin = () => {
    setIsLoading('wechat')
    setTimeout(() => {
      setIsLoading(null)
      onWeChatLogin()
    }, 800)
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto">
      {/* Content */}
      <div className="flex-1 flex flex-col px-8 pt-safe-area-top">
        
        {/* Hero section */}
        <div className="flex-1 flex flex-col justify-center items-center pt-16 pb-8">
          {/* Logo */}
          <div className="mb-10">
            <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-3xl font-serif font-medium text-primary">H</span>
            </div>
          </div>

          {/* Brand name */}
          <h1 className="font-serif text-5xl text-foreground mb-4">Her</h1>

          {/* Tagline */}
          <p className="text-center text-lg text-muted-foreground font-light leading-relaxed max-w-[260px]">
            也许在这里
            <br />
            你会遇见一个很特别的人
          </p>
        </div>

        {/* Login buttons */}
        <div className="pb-10 space-y-3">
          
          {/* Primary: One-click login */}
          <button
            onClick={handleOneClickLogin}
            disabled={isLoading !== null}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium transition-all active:scale-[0.98] disabled:opacity-70 flex items-center justify-center gap-3"
          >
            {isLoading === 'oneclick' ? (
              <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
            ) : (
              <>
                <Smartphone className="w-5 h-5" />
                本机号码一键登录
              </>
            )}
          </button>

          {/* Secondary: WeChat login */}
          <button
            onClick={handleWeChatLogin}
            disabled={isLoading !== null}
            className="w-full py-4 bg-card rounded-2xl border border-border text-foreground font-medium transition-all active:scale-[0.98] disabled:opacity-70 flex items-center justify-center gap-3"
          >
            {isLoading === 'wechat' ? (
              <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            ) : (
              <>
                <MessageCircle className="w-5 h-5 text-primary" />
                微信登录
              </>
            )}
          </button>

          {/* Tertiary: Phone login */}
          <button
            onClick={onPhoneLogin}
            disabled={isLoading !== null}
            className="w-full py-3 flex items-center justify-center gap-1 text-sm font-medium text-primary"
          >
            手机号登录
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Footer */}
        <div className="pb-8 safe-area-bottom">
          <p className="text-center text-xs text-muted-foreground leading-relaxed">
            登录即表示同意
            <button className="underline underline-offset-2 mx-1">用户协议</button>
            和
            <button className="underline underline-offset-2 mx-1">隐私政策</button>
          </p>
        </div>
      </div>
    </div>
  )
}
