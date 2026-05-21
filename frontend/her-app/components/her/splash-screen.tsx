'use client'

import { useEffect, useState } from 'react'
import { XiaoyaAvatar } from '@/components/her/ui/xiaoya-avatar'

interface SplashScreenProps {
  onComplete: () => void
}

export default function SplashScreen({ onComplete }: SplashScreenProps) {
  const [stage, setStage] = useState<'initial' | 'reveal' | 'tagline' | 'cta'>('initial')

  useEffect(() => {
    const timer0 = setTimeout(() => setStage('reveal'), 100)
    const timer1 = setTimeout(() => setStage('tagline'), 1200)
    const timer2 = setTimeout(() => setStage('cta'), 2200)
    
    return () => {
      clearTimeout(timer0)
      clearTimeout(timer1)
      clearTimeout(timer2)
    }
  }, [])

  return (
    <div className="min-h-screen max-w-md mx-auto relative overflow-hidden bg-background">
      {/* Subtle warm background */}
      <div className="absolute inset-0 bg-gradient-to-b from-rose/5 via-background to-gold/5" />
      
      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-8">
        
        {/* Brand mark */}
        <div
          className={`mb-12 transition-all duration-1000 ease-out ${
            stage === 'initial' ? 'opacity-0 scale-90' : 'opacity-100 scale-100'
          }`}
        >
          <XiaoyaAvatar size={128} priority />
        </div>

        {/* Brand wordmark */}
        <h1 
          className={`font-serif text-5xl text-foreground mb-2 tracking-tight transition-all duration-1000 ease-out ${
            stage === 'initial' ? 'opacity-0 translate-y-6' : 'opacity-100 translate-y-0'
          }`}
        >
          小雅
        </h1>

        {/* Subtle tagline */}
        <p 
          className={`text-sm text-muted-foreground tracking-widest mb-16 transition-all duration-1000 delay-300 ease-out ${
            stage !== 'cta' && stage !== 'tagline' ? 'opacity-0 translate-y-4' : 'opacity-100 translate-y-0'
          }`}
        >
          你的专属红娘
        </p>

        {/* Hero statement */}
        <div 
          className={`text-center max-w-xs transition-all duration-1000 delay-500 ease-out ${
            stage !== 'cta' && stage !== 'tagline' ? 'opacity-0 translate-y-8' : 'opacity-100 translate-y-0'
          }`}
        >
          <p className="font-serif text-2xl text-foreground leading-relaxed">
            认真关系
          </p>
          <p className="font-serif text-2xl text-foreground leading-relaxed">
            从认真了解开始
          </p>
        </div>

        {/* CTA Button */}
        <button
          onClick={onComplete}
          className={`mt-16 px-12 py-4 bg-primary rounded-full text-primary-foreground font-medium transition-all duration-700 hover:opacity-90 active:scale-[0.98] ${
            stage !== 'cta' ? 'opacity-0 translate-y-10' : 'opacity-100 translate-y-0'
          }`}
        >
          开始了解
        </button>

        {/* Bottom decorative element */}
        <div 
          className={`absolute bottom-16 left-1/2 -translate-x-1/2 flex items-center gap-4 transition-all duration-1000 delay-700 ${
            stage !== 'cta' ? 'opacity-0' : 'opacity-100'
          }`}
        >
          <div className="w-8 h-px bg-border" />
          <span className="text-xs text-muted-foreground tracking-widest">认真恋爱</span>
          <div className="w-8 h-px bg-border" />
        </div>
      </div>
    </div>
  )
}
