'use client'

import { useState } from 'react'
import { ChevronLeft, Shield, RefreshCw, Phone, MessageCircle } from 'lucide-react'

interface AccountRecoveryPageProps {
  onVerifyComplete: () => void
  onBack: () => void
}

type RecoveryStep = 'method' | 'verify-phone' | 'verify-code' | 'rebind' | 'success'

export default function AccountRecoveryPage({ 
  onVerifyComplete,
  onBack 
}: AccountRecoveryPageProps) {
  const [currentStep, setCurrentStep] = useState<RecoveryStep>('method')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState(['', '', '', '', '', ''])
  const [countdown, setCountdown] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSendCode = () => {
    if (phone.replace(/\D/g, '').length !== 11) {
      setError('请输入正确的手机号')
      return
    }
    
    setIsLoading(true)
    setError(null)
    
    setTimeout(() => {
      setIsLoading(false)
      setCurrentStep('verify-code')
      setCountdown(60)
      
      // Start countdown
      const timer = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            clearInterval(timer)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }, 800)
  }

  const handleVerifyCode = () => {
    const fullCode = code.join('')
    if (fullCode.length !== 6) return
    
    setIsLoading(true)
    setError(null)
    
    setTimeout(() => {
      setIsLoading(false)
      setCurrentStep('success')
    }, 1500)
  }

  const formatPhone = (value: string) => {
    const digits = value.replace(/\D/g, '').slice(0, 11)
    if (digits.length <= 3) return digits
    if (digits.length <= 7) return `${digits.slice(0, 3)} ${digits.slice(3)}`
    return `${digits.slice(0, 3)} ${digits.slice(3, 7)} ${digits.slice(7)}`
  }

  const handleCodeChange = (index: number, value: string) => {
    const digit = value.replace(/\D/g, '').slice(-1)
    const newCode = [...code]
    newCode[index] = digit
    setCode(newCode)
    setError(null)

    if (digit && index < 5) {
      const nextInput = document.getElementById(`code-${index + 1}`)
      nextInput?.focus()
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/20 via-background to-background" />
        <div 
          className="absolute top-32 left-1/2 -translate-x-1/2 w-[350px] h-[350px] rounded-full opacity-15"
          style={{
            background: 'radial-gradient(circle, oklch(0.88 0.06 15 / 0.5) 0%, transparent 70%)',
            filter: 'blur(40px)',
          }}
        />
        <div className="grain-texture absolute inset-0" />
      </div>

      {/* Header */}
      <header className="relative z-10 px-4 pt-14 pb-2">
        <button 
          onClick={() => currentStep === 'method' ? onBack() : setCurrentStep('method')}
          className="w-10 h-10 rounded-full flex items-center justify-center transition-colors"
          style={{ background: 'oklch(0.95 0.01 80)' }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: 'oklch(0.4 0.03 30)' }} />
        </button>
      </header>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col px-8">
        
        {/* Method Selection */}
        {currentStep === 'method' && (
          <>
            {/* Header */}
            <div className="pt-6 pb-8">
              <div className="flex items-center gap-4 mb-6">
                <div 
                  className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{
                    background: 'linear-gradient(135deg, oklch(0.95 0.04 15 / 0.8), oklch(0.92 0.05 80 / 0.5))',
                    boxShadow: '0 4px 16px oklch(0.55 0.12 15 / 0.1)',
                  }}
                >
                  <Shield className="w-6 h-6" style={{ color: 'oklch(0.55 0.12 15)' }} />
                </div>
                <div>
                  <h1 
                    className="editorial-title text-2xl mb-1"
                    style={{ color: 'oklch(0.3 0.03 25)' }}
                  >
                    恢复访问
                  </h1>
                  <p className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
                    我们来帮你找回账号
                  </p>
                </div>
              </div>

              <p 
                className="text-sm leading-relaxed"
                style={{ color: 'oklch(0.5 0.03 30)' }}
              >
                别担心，你的资料和聊天记录都安全保存着。选择一种方式重新确认身份，即可恢复访问。
              </p>
            </div>

            {/* Recovery options */}
            <div className="space-y-3 flex-1">
              <button
                onClick={() => setCurrentStep('verify-phone')}
                className="w-full p-5 rounded-2xl flex items-center gap-4 text-left transition-all active:scale-[0.99]"
                style={{
                  background: 'oklch(0.98 0.008 80)',
                  border: '2px solid oklch(0.9 0.02 80)',
                }}
              >
                <div 
                  className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{ background: 'oklch(0.94 0.03 15 / 0.5)' }}
                >
                  <Phone className="w-5 h-5" style={{ color: 'oklch(0.55 0.12 15)' }} />
                </div>
                <div className="flex-1">
                  <div className="font-medium mb-1" style={{ color: 'oklch(0.35 0.03 30)' }}>
                    手机号验证
                  </div>
                  <div className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
                    使用已绑定的手机号接收验证码
                  </div>
                </div>
              </button>

              <button
                className="w-full p-5 rounded-2xl flex items-center gap-4 text-left transition-all active:scale-[0.99]"
                style={{
                  background: 'oklch(0.98 0.008 80)',
                  border: '2px solid oklch(0.9 0.02 80)',
                }}
              >
                <div 
                  className="w-12 h-12 rounded-xl flex items-center justify-center"
                  style={{ background: 'oklch(0.9 0.04 145 / 0.3)' }}
                >
                  <MessageCircle className="w-5 h-5" style={{ color: 'oklch(0.55 0.15 145)' }} />
                </div>
                <div className="flex-1">
                  <div className="font-medium mb-1" style={{ color: 'oklch(0.35 0.03 30)' }}>
                    微信验证
                  </div>
                  <div className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
                    使用已绑定的微信账号验证身份
                  </div>
                </div>
              </button>
            </div>

            {/* Help hint */}
            <div className="py-8 safe-area-bottom">
              <p 
                className="text-center text-xs"
                style={{ color: 'oklch(0.6 0.02 30)' }}
              >
                如需帮助，请联系客服
              </p>
            </div>
          </>
        )}

        {/* Phone Input */}
        {currentStep === 'verify-phone' && (
          <>
            <div className="pt-6 pb-8">
              <h1 
                className="editorial-title text-2xl mb-3"
                style={{ color: 'oklch(0.3 0.03 25)' }}
              >
                输入绑定的手机号
              </h1>
              <p 
                className="text-sm"
                style={{ color: 'oklch(0.55 0.02 30)' }}
              >
                我们将发送验证码确认你的身份
              </p>
            </div>

            <div className="mb-6">
              <div 
                className="flex items-center px-5 py-4 rounded-2xl"
                style={{ 
                  background: 'oklch(0.98 0.008 80)',
                  border: '2px solid oklch(0.9 0.02 80)',
                }}
              >
                <span 
                  className="text-lg font-medium mr-3 pr-3"
                  style={{ 
                    color: 'oklch(0.4 0.03 30)',
                    borderRight: '1px solid oklch(0.88 0.02 80)',
                  }}
                >
                  +86
                </span>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => {
                    setPhone(formatPhone(e.target.value))
                    setError(null)
                  }}
                  placeholder="请输入手机号"
                  className="flex-1 text-lg bg-transparent outline-none"
                  style={{ color: 'oklch(0.3 0.03 25)' }}
                />
              </div>
              {error && (
                <p className="mt-3 text-sm px-2" style={{ color: 'oklch(0.55 0.15 20)' }}>
                  {error}
                </p>
              )}
            </div>

            <div className="flex-1" />

            <div className="pb-8 safe-area-bottom">
              <button
                onClick={handleSendCode}
                disabled={phone.replace(/\D/g, '').length !== 11 || isLoading}
                className="w-full py-4 rounded-2xl font-medium text-base transition-all duration-300 active:scale-[0.98] disabled:opacity-50 flex items-center justify-center"
                style={{
                  background: phone.replace(/\D/g, '').length === 11
                    ? 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))'
                    : 'oklch(0.9 0.02 80)',
                  color: phone.replace(/\D/g, '').length === 11 ? 'oklch(0.98 0.005 85)' : 'oklch(0.6 0.02 30)',
                  boxShadow: phone.replace(/\D/g, '').length === 11 ? '0 4px 20px oklch(0.55 0.12 15 / 0.3)' : 'none',
                }}
              >
                {isLoading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  '发送验证码'
                )}
              </button>
            </div>
          </>
        )}

        {/* Code Verification */}
        {currentStep === 'verify-code' && (
          <>
            <div className="pt-6 pb-8">
              <h1 
                className="editorial-title text-2xl mb-3"
                style={{ color: 'oklch(0.3 0.03 25)' }}
              >
                输入验证码
              </h1>
              <p 
                className="text-sm"
                style={{ color: 'oklch(0.55 0.02 30)' }}
              >
                验证码已发送至 {phone.replace(/(\d{3})\s*\d{4}\s*(\d{4})/, '$1****$2')}
              </p>
            </div>

            <div className="mb-6">
              <div className="flex justify-between gap-3">
                {code.map((digit, index) => (
                  <input
                    key={index}
                    id={`code-${index}`}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleCodeChange(index, e.target.value)}
                    className="w-12 h-14 text-center text-2xl font-medium rounded-xl outline-none"
                    style={{ 
                      background: digit ? 'oklch(0.96 0.02 15 / 0.5)' : 'oklch(0.97 0.008 80)',
                      border: `2px solid ${digit ? 'oklch(0.7 0.1 15)' : 'oklch(0.9 0.02 80)'}`,
                      color: 'oklch(0.3 0.05 20)',
                    }}
                  />
                ))}
              </div>
            </div>

            <div className="flex items-center justify-center gap-2 py-4">
              {countdown > 0 ? (
                <span className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
                  {countdown}秒后可重新发送
                </span>
              ) : (
                <button
                  onClick={() => {
                    setCountdown(60)
                    // Start countdown again
                    const timer = setInterval(() => {
                      setCountdown(prev => {
                        if (prev <= 1) {
                          clearInterval(timer)
                          return 0
                        }
                        return prev - 1
                      })
                    }, 1000)
                  }}
                  className="flex items-center gap-2 text-sm font-medium"
                  style={{ color: 'oklch(0.55 0.1 15)' }}
                >
                  <RefreshCw className="w-4 h-4" />
                  重新发送
                </button>
              )}
            </div>

            <div className="flex-1" />

            <div className="pb-8 safe-area-bottom">
              <button
                onClick={handleVerifyCode}
                disabled={code.join('').length !== 6 || isLoading}
                className="w-full py-4 rounded-2xl font-medium text-base transition-all duration-300 active:scale-[0.98] disabled:opacity-50 flex items-center justify-center"
                style={{
                  background: code.join('').length === 6
                    ? 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))'
                    : 'oklch(0.9 0.02 80)',
                  color: code.join('').length === 6 ? 'oklch(0.98 0.005 85)' : 'oklch(0.6 0.02 30)',
                  boxShadow: code.join('').length === 6 ? '0 4px 20px oklch(0.55 0.12 15 / 0.3)' : 'none',
                }}
              >
                {isLoading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  '验证'
                )}
              </button>
            </div>
          </>
        )}

        {/* Success */}
        {currentStep === 'success' && (
          <div className="flex-1 flex flex-col items-center justify-center">
            <div 
              className="w-20 h-20 rounded-full flex items-center justify-center mb-6"
              style={{
                background: 'linear-gradient(135deg, oklch(0.92 0.08 145 / 0.3), oklch(0.88 0.06 145 / 0.2))',
                boxShadow: '0 8px 32px oklch(0.55 0.15 145 / 0.15)',
              }}
            >
              <svg className="w-10 h-10" viewBox="0 0 24 24" fill="none">
                <path 
                  d="M5 12L10 17L19 7" 
                  stroke="oklch(0.5 0.15 145)" 
                  strokeWidth="2.5" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                />
              </svg>
            </div>

            <h2 
              className="editorial-title text-2xl mb-3 text-center"
              style={{ color: 'oklch(0.3 0.03 25)' }}
            >
              身份验证成功
            </h2>
            <p 
              className="text-sm text-center mb-10"
              style={{ color: 'oklch(0.55 0.02 30)' }}
            >
              欢迎回来，你的账号已恢复访问
            </p>

            <button
              onClick={onVerifyComplete}
              className="w-full py-4 rounded-2xl font-medium text-base transition-all duration-300 active:scale-[0.98]"
              style={{
                background: 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))',
                color: 'oklch(0.98 0.005 85)',
                boxShadow: '0 4px 20px oklch(0.55 0.12 15 / 0.3)',
              }}
            >
              进入 Her
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
