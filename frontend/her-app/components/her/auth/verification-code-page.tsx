'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { ChevronLeft, RefreshCw } from 'lucide-react'

interface VerificationCodePageProps {
  phone: string // e.g., "13812341234"
  onVerify: (code: string) => void | Promise<void>
  onResend: () => void | Promise<void>
  onBack: () => void
}

type ErrorType = 'invalid' | 'expired' | 'too_frequent' | 'network' | null

export default function VerificationCodePage({ 
  phone,
  onVerify, 
  onResend,
  onBack 
}: VerificationCodePageProps) {
  const [code, setCode] = useState(['', '', '', '', '', ''])
  const [countdown, setCountdown] = useState(60)
  const [isVerifying, setIsVerifying] = useState(false)
  const [error, setError] = useState<ErrorType>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isResending, setIsResending] = useState(false)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  // Format phone for display
  const maskedPhone = phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')

  // Countdown timer
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [countdown])

  // Auto-focus first input
  useEffect(() => {
    inputRefs.current[0]?.focus()
  }, [])

  // Auto-verify when all digits entered
  const handleVerify = useCallback(async (fullCode: string) => {
    setIsVerifying(true)
    setError(null)
    setErrorMessage(null)
    try {
      await onVerify(fullCode)
    } catch (err) {
      const message = err instanceof Error ? err.message : '验证失败，请稍后重试'
      setErrorMessage(message)
      if (/过期/.test(message)) setError('expired')
      else if (/频繁/.test(message)) setError('too_frequent')
      else if (/验证码|无效/.test(message)) setError('invalid')
      else setError('network')
      setCode(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    } finally {
      setIsVerifying(false)
    }
  }, [onVerify])

  useEffect(() => {
    const fullCode = code.join('')
    if (fullCode.length === 6 && !isVerifying) {
      handleVerify(fullCode)
    }
  }, [code, isVerifying, handleVerify])

  const handleChange = (index: number, value: string) => {
    // Only allow digits
    const digit = value.replace(/\D/g, '').slice(-1)
    
    const newCode = [...code]
    newCode[index] = digit
    setCode(newCode)
    setError(null)
    setErrorMessage(null)

    // Auto-focus next input
    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus()
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault()
    const pastedData = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pastedData) {
      const newCode = [...code]
      pastedData.split('').forEach((digit, i) => {
        if (i < 6) newCode[i] = digit
      })
      setCode(newCode)
      inputRefs.current[Math.min(pastedData.length, 5)]?.focus()
    }
  }

  const handleResend = () => {
    if (countdown > 0 || isResending) return
    
    setIsResending(true)
    setError(null)
    setErrorMessage(null)
    Promise.resolve(onResend())
      .then(() => {
        setCountdown(60)
        setCode(['', '', '', '', '', ''])
        inputRefs.current[0]?.focus()
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : '发送失败，请稍后重试'
        setErrorMessage(message)
        if (/频繁/.test(message)) setError('too_frequent')
        else setError('network')
      })
      .finally(() => {
        setIsResending(false)
      })
  }

  const errorMessages: Record<string, string> = {
    invalid: '验证码错误，请重新输入',
    expired: '验证码已过期，请重新获取',
    too_frequent: '发送太频繁，请稍后再试',
    network: '网络错误，请检查网络后重试',
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/20 via-background to-background" />
        <div 
          className="absolute top-32 left-1/2 -translate-x-1/2 w-[300px] h-[300px] rounded-full opacity-15"
          style={{
            background: 'radial-gradient(circle, oklch(0.85 0.06 15 / 0.5) 0%, transparent 70%)',
            filter: 'blur(40px)',
          }}
        />
        <div className="grain-texture absolute inset-0" />
      </div>

      {/* Header */}
      <header className="relative z-10 px-4 pt-14 pb-2">
        <button 
          onClick={onBack}
          className="w-10 h-10 rounded-full flex items-center justify-center transition-colors"
          style={{ background: 'oklch(0.95 0.01 80)' }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: 'oklch(0.4 0.03 30)' }} />
        </button>
      </header>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col px-8">
        
        {/* Title section */}
        <div className="pt-6 pb-8">
          <h1 
            className="editorial-title text-3xl mb-3"
            style={{ color: 'oklch(0.3 0.03 25)' }}
          >
            输入验证码
          </h1>
          <p 
            className="text-sm"
            style={{ color: 'oklch(0.55 0.02 30)' }}
          >
            验证码已发送至 <span className="font-medium" style={{ color: 'oklch(0.4 0.03 25)' }}>{maskedPhone}</span>
          </p>
        </div>

        {/* Code input */}
        <div className="mb-6">
          <div className="flex justify-between gap-3" onPaste={handlePaste}>
            {code.map((digit, index) => (
              <input
                key={index}
                ref={(el) => { inputRefs.current[index] = el }}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={digit}
                onChange={(e) => handleChange(index, e.target.value)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                disabled={isVerifying}
                className="w-12 h-14 text-center text-2xl font-medium rounded-xl transition-all duration-200 outline-none"
                style={{ 
                  background: digit ? 'oklch(0.96 0.02 15 / 0.5)' : 'oklch(0.97 0.008 80)',
                  border: `2px solid ${error ? 'oklch(0.65 0.15 20)' : digit ? 'oklch(0.7 0.1 15)' : 'oklch(0.9 0.02 80)'}`,
                  color: 'oklch(0.3 0.05 20)',
                }}
              />
            ))}
          </div>

          {/* Error message */}
          {error && (
            <p 
              className="mt-4 text-sm text-center"
              style={{ color: 'oklch(0.55 0.15 20)' }}
            >
              {errorMessage || errorMessages[error]}
            </p>
          )}

          {/* Loading state */}
          {isVerifying && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <div 
                className="w-4 h-4 border-2 rounded-full animate-spin"
                style={{ borderColor: 'oklch(0.8 0.05 15)', borderTopColor: 'oklch(0.55 0.12 15)' }}
              />
              <span className="text-sm" style={{ color: 'oklch(0.5 0.03 30)' }}>验证中...</span>
            </div>
          )}
        </div>

        {/* Resend section */}
        <div className="flex items-center justify-center gap-2 py-4">
          {countdown > 0 ? (
            <span className="text-sm" style={{ color: 'oklch(0.55 0.02 30)' }}>
              {countdown}秒后可重新发送
            </span>
          ) : (
            <button
              onClick={handleResend}
              disabled={isResending}
              className="flex items-center gap-2 text-sm font-medium transition-colors"
              style={{ color: 'oklch(0.55 0.1 15)' }}
            >
              {isResending ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  发送中...
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4" />
                  重新发送验证码
                </>
              )}
            </button>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Help text */}
        <div className="pb-10 safe-area-bottom">
          <p 
            className="text-center text-xs leading-relaxed"
            style={{ color: 'oklch(0.6 0.02 30)' }}
          >
            收不到验证码？请检查短信是否被拦截
          </p>
        </div>
      </div>
    </div>
  )
}
