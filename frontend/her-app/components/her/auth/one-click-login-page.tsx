'use client'

import { useState } from 'react'
import { ChevronLeft, Shield, Smartphone } from 'lucide-react'

interface OneClickLoginPageProps {
  phoneNumber?: string
  onLogin: () => void | Promise<void>
  onUseOtherPhone: () => void
  onBack: () => void
}

export default function OneClickLoginPage({ 
  phoneNumber = "138****1234",
  onLogin, 
  onUseOtherPhone,
  onBack 
}: OneClickLoginPageProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleLogin = async () => {
    setIsLoading(true)
    setError(null)
    try {
      await onLogin()
    } catch (err) {
      setError(err instanceof Error ? err.message : '网络请求失败，请重试或使用其他方式登录')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto">
      {/* Header */}
      <header className="px-4 pt-14 pb-2">
        <button 
          onClick={onBack}
          className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center"
        >
          <ChevronLeft className="w-5 h-5 text-foreground" />
        </button>
      </header>

      {/* Content */}
      <div className="flex-1 flex flex-col px-8">
        
        {/* Main content */}
        <div className="flex-1 flex flex-col items-center pt-12">
          
          {/* Phone icon */}
          <div className="relative mb-8">
            <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
              <Smartphone className="w-9 h-9 text-primary" />
            </div>
          </div>

          {/* Title */}
          <h1 className="font-serif text-2xl text-foreground mb-3 text-center">
            本机号码一键登录
          </h1>

          {/* Phone number */}
          <div className="text-2xl font-medium text-foreground tracking-wider mb-4">
            {phoneNumber}
          </div>

          {/* Security badge */}
          <div className="flex items-center gap-2 px-4 py-2 bg-secondary rounded-full mb-8">
            <Shield className="w-4 h-4 text-primary" />
            <span className="text-sm text-muted-foreground">
              运营商安全认证
            </span>
          </div>

          {/* Error */}
          {error && (
            <div className="w-full px-4 py-3 bg-destructive/10 rounded-xl mb-6 text-center text-sm text-destructive">
              {error}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="pb-10 space-y-4">
          <button
            onClick={handleLogin}
            disabled={isLoading}
            className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium transition-all active:scale-[0.98] disabled:opacity-70 flex items-center justify-center"
          >
            {isLoading ? (
              <div className="flex items-center gap-3">
                <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                <span>正在验证...</span>
              </div>
            ) : (
              '一键登录'
            )}
          </button>

          <button
            onClick={onUseOtherPhone}
            disabled={isLoading}
            className="w-full py-3.5 text-sm font-medium text-primary"
          >
            使用其他手机号
          </button>
        </div>

        {/* Footer */}
        <div className="pb-8 safe-area-bottom">
          <p className="text-center text-xs text-muted-foreground">
            将通过运营商验证本机号码
          </p>
        </div>
      </div>
    </div>
  )
}
