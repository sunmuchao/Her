'use client'

import { useState, useEffect } from 'react'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'

interface NewUserWelcomePageProps {
  onStartProfile: () => void
}

export default function NewUserWelcomePage({ 
  onStartProfile 
}: NewUserWelcomePageProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [showButton, setShowButton] = useState(false)

  useEffect(() => {
    // Staggered reveal animation
    setTimeout(() => setIsVisible(true), 100)
    setTimeout(() => setShowButton(true), 800)
  }, [])

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative overflow-hidden">
      {/* Cinematic background */}
      <div className="absolute inset-0">
        {/* Base warm gradient */}
        <div className="absolute inset-0 bg-gradient-to-b from-rose-soft/50 via-background to-gold-soft/30" />
        
        {/* Soft rose glow top */}
        <div 
          className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[500px] rounded-full opacity-40"
          style={{
            background: 'radial-gradient(circle, oklch(0.9 0.08 15 / 0.6) 0%, transparent 70%)',
            filter: 'blur(60px)',
          }}
        />
        
        {/* Golden glow center */}
        <div 
          className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[400px] h-[400px] rounded-full opacity-30"
          style={{
            background: 'radial-gradient(circle, oklch(0.85 0.1 80 / 0.5) 0%, transparent 70%)',
            filter: 'blur(50px)',
          }}
        />
        
        {/* Bottom warm light */}
        <div 
          className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[500px] h-[300px] rounded-full opacity-25"
          style={{
            background: 'radial-gradient(ellipse, oklch(0.88 0.06 15 / 0.5) 0%, transparent 70%)',
            filter: 'blur(40px)',
          }}
        />

        {/* Grain texture */}
        <div className="grain-texture absolute inset-0" />
      </div>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-10">
        
        {/* Welcome icon */}
        <div 
          className={`mb-8 transition-all duration-1000 ${
            isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}
        >
          <XiaoyaAvatar size={96} priority />
        </div>

        {/* Welcome text */}
        <div 
          className={`text-center mb-10 transition-all duration-1000 delay-200 ${
            isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}
        >
          <h1 
            className="editorial-title text-4xl mb-6"
            style={{ color: 'oklch(0.32 0.05 20)' }}
          >
            欢迎来到小雅
          </h1>
          
          <p 
            className="text-base leading-relaxed mb-4"
            style={{ color: 'oklch(0.5 0.03 30)' }}
          >
            很高兴认识你
          </p>

          <p 
            className="text-base leading-relaxed"
            style={{ color: 'oklch(0.5 0.03 30)' }}
          >
            接下来，我会更了解你
            <br />
            帮你认真遇见合适的人
          </p>
        </div>

        {/* Decorative divider */}
        <div 
          className={`flex items-center gap-4 mb-10 transition-all duration-1000 delay-400 ${
            isVisible ? 'opacity-100' : 'opacity-0'
          }`}
        >
          <div className="w-12 h-px" style={{ background: 'linear-gradient(90deg, transparent, oklch(0.7 0.08 15))' }} />
          <div 
            className="w-2 h-2 rounded-full"
            style={{ background: 'oklch(0.7 0.08 15)' }}
          />
          <div className="w-12 h-px" style={{ background: 'linear-gradient(90deg, oklch(0.7 0.08 15), transparent)' }} />
        </div>

        {/* Value propositions */}
        <div 
          className={`space-y-4 text-center mb-12 transition-all duration-1000 delay-500 ${
            isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}
        >
          {[
            '我会了解你的故事和期待',
            '为你精心筛选每一位推荐',
            '陪伴你建立真诚的连接',
          ].map((text, index) => (
            <p 
              key={index}
              className="text-sm"
              style={{ 
                color: 'oklch(0.55 0.04 25)',
                transitionDelay: `${600 + index * 100}ms`,
              }}
            >
              {text}
            </p>
          ))}
        </div>
      </div>

      {/* CTA Button */}
      <div 
        className={`relative z-10 px-8 pb-12 safe-area-bottom transition-all duration-700 ${
          showButton ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
        }`}
      >
        <button
          onClick={onStartProfile}
          className="w-full py-4 rounded-2xl font-medium text-base transition-all duration-300 active:scale-[0.98] flex items-center justify-center gap-2"
          style={{
            background: 'linear-gradient(135deg, oklch(0.55 0.12 15), oklch(0.5 0.14 20))',
            color: 'oklch(0.98 0.005 85)',
            boxShadow: '0 4px 24px oklch(0.55 0.12 15 / 0.35)',
          }}
        >
          开始建立我的资料
        </button>
      </div>
    </div>
  )
}
