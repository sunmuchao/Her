'use client'

import { useState, useRef } from 'react'
import { ChevronLeft, MessageCircle } from 'lucide-react'

interface PhoneLoginPageProps {
  onSubmit: (phone: string) => void
  onWeChatLogin: () => void
  onBack: () => void
}

export default function PhoneLoginPage({ 
  onSubmit, 
  onWeChatLogin,
  onBack 
}: PhoneLoginPageProps) {
  const [phone, setPhone] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const formatPhone = (value: string) => {
    const digits = value.replace(/\D/g, '').slice(0, 11)
    if (digits.length <= 3) return digits
    if (digits.length <= 7) return `${digits.slice(0, 3)} ${digits.slice(3)}`
    return `${digits.slice(0, 3)} ${digits.slice(3, 7)} ${digits.slice(7)}`
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatPhone(e.target.value)
    setPhone(formatted)
    setError(null)
  }

  const validatePhone = () => {
    const digits = phone.replace(/\D/g, '')
    if (digits.length !== 11) {
      setError('请输入11位手机号')
      return false
    }
    if (!/^1[3-9]\d{9}$/.test(digits)) {
      setError('请输入正确的手机号')
      return false
    }
    return true
  }

  const handleSubmit = () => {
    if (!validatePhone()) return
    setIsLoading(true)
    setTimeout(() => {
      setIsLoading(false)
      onSubmit(phone.replace(/\D/g, ''))
    }, 800)
  }

  const isValid = phone.replace(/\D/g, '').length === 11

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
        
        {/* Title */}
        <div className="pt-6 pb-10">
          <h1 className="font-serif text-2xl text-foreground mb-3">
            输入手机号
          </h1>
          <p className="text-sm text-muted-foreground">
            未注册的手机号验证后将自动创建账号
          </p>
        </div>

        {/* Phone input */}
        <div className="mb-6">
          <div 
            className={`flex items-center px-5 py-4 rounded-2xl border-2 transition-colors ${
              isFocused ? 'border-primary bg-card' : 'border-border bg-secondary/30'
            }`}
          >
            <span className="text-lg font-medium text-foreground mr-3 pr-3 border-r border-border">
              +86
            </span>
            
            <input
              ref={inputRef}
              type="tel"
              value={phone}
              onChange={handleChange}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder="请输入手机号"
              className="flex-1 text-lg bg-transparent outline-none text-foreground placeholder:text-muted-foreground"
              autoComplete="tel"
            />

            {phone && (
              <button
                onClick={() => {
                  setPhone('')
                  setError(null)
                  inputRef.current?.focus()
                }}
                className="w-6 h-6 rounded-full bg-muted flex items-center justify-center ml-2 text-muted-foreground"
              >
                ×
              </button>
            )}
          </div>

          {error && (
            <p className="mt-3 text-sm px-2 text-destructive">{error}</p>
          )}
        </div>

        <div className="flex-1" />

        {/* Actions */}
        <div className="pb-6 space-y-4">
          <button
            onClick={handleSubmit}
            disabled={!isValid || isLoading}
            className={`w-full py-4 rounded-2xl font-medium transition-all active:scale-[0.98] flex items-center justify-center ${
              isValid 
                ? 'bg-primary text-primary-foreground' 
                : 'bg-secondary text-muted-foreground'
            }`}
          >
            {isLoading ? (
              <div className="w-5 h-5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
            ) : (
              '获取验证码'
            )}
          </button>

          <button
            onClick={onWeChatLogin}
            className="w-full py-3 flex items-center justify-center gap-2 text-sm font-medium text-muted-foreground"
          >
            <MessageCircle className="w-4 h-4 text-primary" />
            使用微信登录
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
