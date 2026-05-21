'use client'

import { useState } from 'react'
import { ChevronLeft, User } from 'lucide-react'

interface WeChatBindingPageProps {
  wechatNickname?: string
  wechatAvatar?: string
  onBindPhone: () => void | Promise<void>
  onSkip?: () => void | Promise<void>
  onBack: () => void
}

export default function WeChatBindingPage({ 
  wechatNickname = "微信用户",
  wechatAvatar,
  onBindPhone, 
  onSkip,
  onBack 
}: WeChatBindingPageProps) {
  const [isLoading, setIsLoading] = useState(false)

  const handleBindPhone = () => {
    setIsLoading(true)
    Promise.resolve(onBindPhone()).finally(() => {
      setIsLoading(false)
    })
  }

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Soft background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/25 via-background to-gold-soft/10" />
        <div 
          className="absolute top-24 left-1/2 -translate-x-1/2 w-[400px] h-[400px] rounded-full opacity-20"
          style={{
            background: 'radial-gradient(circle, oklch(0.88 0.06 15 / 0.5) 0%, transparent 70%)',
            filter: 'blur(50px)',
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
        
        {/* Main content area */}
        <div className="flex-1 flex flex-col items-center pt-8">
          
          {/* WeChat avatar */}
          <div className="relative mb-6">
            <div 
              className="w-24 h-24 rounded-full flex items-center justify-center overflow-hidden"
              style={{
                background: 'linear-gradient(135deg, oklch(0.55 0.15 145 / 0.1), oklch(0.55 0.15 145 / 0.05))',
                border: '3px solid oklch(0.55 0.15 145 / 0.3)',
                boxShadow: '0 8px 32px oklch(0.55 0.15 145 / 0.15)',
              }}
            >
              {wechatAvatar ? (
                <img src={wechatAvatar} alt="" className="w-full h-full object-cover" />
              ) : (
                <User className="w-12 h-12" style={{ color: 'oklch(0.55 0.15 145)' }} />
              )}
            </div>
            
            {/* WeChat badge */}
            <div 
              className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full flex items-center justify-center"
              style={{ 
                background: 'oklch(0.55 0.15 145)',
                boxShadow: '0 2px 8px oklch(0.55 0.15 145 / 0.4)',
              }}
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="white">
                <path d="M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.29.295a.328.328 0 0 0 .186-.059l1.873-1.12a.593.593 0 0 1 .452-.076c1.022.275 2.118.426 3.113.426 4.8 0 8.691-3.288 8.691-7.342 0-4.054-3.891-7.374-8.691-7.374zm10.987 7.342c0 2.877-1.776 5.447-4.496 6.847a9.026 9.026 0 0 1-.482 2.542c-.32.822-.888 1.612-1.503 2.228l.012.017-.045-.017a.474.474 0 0 1-.245.067.293.293 0 0 1-.29-.295c0-.072.023-.143.048-.213l.36-1.354a.592.592 0 0 0-.207-.618 7.616 7.616 0 0 1-2.17-2.293c1.01.15 2.071.228 3.155.228 5.41 0 9.838-3.627 9.838-8.134 0-.296-.024-.587-.06-.875 1.553 1.303 2.52 3.1 2.52 5.095 0 2.212-1.17 4.203-3.002 5.55a.59.59 0 0 0-.213.665l.39 1.48c.019.07.048.141.048.213 0 .163-.13.295-.29.295a.328.328 0 0 1-.186-.059l-1.873-1.12a.593.593 0 0 0-.452-.076 10.46 10.46 0 0 1-2.356.271c-.123 0-.244-.005-.366-.009-.01-.022-.013-.047-.024-.068z"/>
              </svg>
            </div>
          </div>

          {/* Welcome message */}
          <h2 
            className="text-lg font-medium mb-2"
            style={{ color: 'oklch(0.35 0.03 30)' }}
          >
            欢迎，{wechatNickname}
          </h2>
          
          <p 
            className="text-sm mb-10"
            style={{ color: 'oklch(0.55 0.02 30)' }}
          >
            微信授权成功
          </p>

          {/* Bind phone card */}
          <div 
            className="w-full rounded-2xl p-6"
            style={{
              background: 'linear-gradient(135deg, oklch(0.98 0.01 80), oklch(0.96 0.02 15 / 0.3))',
              border: '1px solid oklch(0.9 0.03 15 / 0.5)',
              boxShadow: '0 4px 20px oklch(0.55 0.12 15 / 0.08)',
            }}
          >
            <h3 
              className="text-base font-medium mb-2"
              style={{ color: 'oklch(0.35 0.05 20)' }}
            >
              绑定手机号
            </h3>
            <p 
              className="text-sm leading-relaxed mb-6"
              style={{ color: 'oklch(0.5 0.03 30)' }}
            >
              绑定手机号可保护账号安全，支持多种方式登录，万一丢失微信也能找回账号
            </p>

            {/* Benefits list */}
            <div className="space-y-3 mb-6">
              {[
                '账号安全保障',
                '支持手机号登录',
                '账号找回更便捷',
              ].map((benefit, index) => (
                <div key={index} className="flex items-center gap-3">
                  <div 
                    className="w-5 h-5 rounded-full flex items-center justify-center"
                    style={{ background: 'oklch(0.92 0.04 15)' }}
                  >
                    <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
                      <path 
                        d="M2 6L5 9L10 3" 
                        stroke="oklch(0.55 0.12 15)" 
                        strokeWidth="2" 
                        strokeLinecap="round" 
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                  <span className="text-sm" style={{ color: 'oklch(0.45 0.03 30)' }}>
                    {benefit}
                  </span>
                </div>
              ))}
            </div>

            {/* Bind button */}
            <button
              onClick={handleBindPhone}
              disabled={isLoading}
              className="w-full py-3.5 rounded-xl font-medium text-sm transition-all duration-300 active:scale-[0.98]"
              style={{
                background: 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))',
                color: 'oklch(0.98 0.005 85)',
                boxShadow: '0 4px 16px oklch(0.55 0.12 15 / 0.3)',
              }}
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto" />
              ) : (
                '绑定手机号'
              )}
            </button>
          </div>
        </div>

        {/* Skip option */}
        {onSkip && (
          <div className="py-6">
            <button
              onClick={onSkip}
              className="w-full py-3 text-sm font-medium transition-colors"
              style={{ color: 'oklch(0.55 0.03 30)' }}
            >
              暂时跳过
            </button>
          </div>
        )}

        {/* Footer hint */}
        <div className="pb-8 safe-area-bottom">
          <p 
            className="text-center text-xs"
            style={{ color: 'oklch(0.6 0.02 30)' }}
          >
            绑定手机号后可使用更多功能
          </p>
        </div>
      </div>
    </div>
  )
}
