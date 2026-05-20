'use client'

import { useEffect, useState } from 'react'

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
    <div className="min-h-screen max-w-md mx-auto relative overflow-hidden bg-[#1a1714]">
      {/* Cinematic background layers */}
      <div className="absolute inset-0">
        {/* Deep base gradient - warm dark tones */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#2a2420] via-[#1a1714] to-[#0f0d0b]" />
        
        {/* Warm light bloom from top - like soft morning light */}
        <div 
          className={`absolute -top-32 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full transition-all duration-[2000ms] ease-out ${
            stage !== 'initial' ? 'opacity-100 scale-100' : 'opacity-0 scale-75'
          }`}
          style={{
            background: 'radial-gradient(ellipse at center, rgba(212, 165, 141, 0.25) 0%, rgba(184, 133, 109, 0.15) 30%, rgba(139, 90, 70, 0.08) 50%, transparent 70%)'
          }}
        />
        
        {/* Rose accent glow - subtle romantic warmth */}
        <div 
          className={`absolute top-1/3 right-0 w-[400px] h-[400px] rounded-full transition-all duration-[2500ms] delay-300 ease-out ${
            stage !== 'initial' ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-20'
          }`}
          style={{
            background: 'radial-gradient(ellipse at center, rgba(168, 119, 107, 0.12) 0%, transparent 60%)'
          }}
        />
        
        {/* Gold accent - champagne shimmer */}
        <div 
          className={`absolute bottom-1/4 left-0 w-[350px] h-[350px] rounded-full transition-all duration-[2500ms] delay-500 ease-out ${
            stage !== 'initial' ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-20'
          }`}
          style={{
            background: 'radial-gradient(ellipse at center, rgba(196, 169, 132, 0.1) 0%, transparent 60%)'
          }}
        />
        
        {/* Subtle film grain overlay */}
        <div className="absolute inset-0 opacity-[0.03] grain-texture" />
        
        {/* Vignette effect for cinematic depth */}
        <div 
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(ellipse at center, transparent 30%, rgba(15,13,11,0.4) 100%)'
          }}
        />
      </div>
      
      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-8">
        
        {/* Brand mark - elegant monogram */}
        <div 
          className={`relative mb-12 transition-all duration-[1500ms] ease-out ${
            stage === 'initial' ? 'opacity-0 scale-90 blur-sm' : 'opacity-100 scale-100 blur-0'
          }`}
        >
          {/* Outer glow ring */}
          <div 
            className={`absolute inset-0 w-28 h-28 rounded-full transition-all duration-[2000ms] delay-200 ${
              stage !== 'initial' ? 'opacity-100' : 'opacity-0'
            }`}
            style={{
              background: 'radial-gradient(circle, rgba(196, 169, 132, 0.15) 0%, transparent 70%)',
              transform: 'scale(1.8)'
            }}
          />
          
          {/* Logo container with premium finish */}
          <div className="relative w-28 h-28 rounded-full bg-gradient-to-br from-[#c8a888] via-[#b89878] to-[#a8876b] flex items-center justify-center shadow-2xl">
            {/* Inner highlight for dimension */}
            <div className="absolute inset-1 rounded-full bg-gradient-to-br from-[#d4b89a]/40 via-transparent to-transparent" />
            
            {/* Brand letter with editorial serif */}
            <span className="relative editorial-title text-5xl text-[#1a1714] tracking-tight">H</span>
          </div>
          
          {/* Subtle reflection */}
          <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 w-20 h-8 rounded-full bg-[#c8a888]/5 blur-xl" />
        </div>

        {/* Brand wordmark */}
        <h1 
          className={`editorial-title text-6xl text-[#e8ddd4] mb-2 tracking-tight transition-all duration-[1200ms] ease-out ${
            stage === 'initial' ? 'opacity-0 translate-y-6' : 'opacity-100 translate-y-0'
          }`}
          style={{ textShadow: '0 2px 20px rgba(196, 169, 132, 0.2)' }}
        >
          Her
        </h1>

        {/* Subtle tagline */}
        <p 
          className={`text-sm text-[#a09080] font-light tracking-[0.3em] uppercase mb-20 transition-all duration-[1200ms] delay-300 ease-out ${
            stage !== 'cta' && stage !== 'tagline' ? 'opacity-0 translate-y-4' : 'opacity-100 translate-y-0'
          }`}
        >
          遇见心动
        </p>

        {/* Hero statement - cinematic editorial typography */}
        <div 
          className={`text-center max-w-sm transition-all duration-[1500ms] delay-500 ease-out ${
            stage !== 'cta' && stage !== 'tagline' ? 'opacity-0 translate-y-8' : 'opacity-100 translate-y-0'
          }`}
        >
          <p 
            className="editorial-title text-3xl text-[#d4c4b8] leading-[1.6] mb-3"
            style={{ textShadow: '0 2px 30px rgba(0,0,0,0.3)' }}
          >
            也许在这里
          </p>
          <p 
            className="editorial-title text-3xl text-[#d4c4b8] leading-[1.6]"
            style={{ textShadow: '0 2px 30px rgba(0,0,0,0.3)' }}
          >
            你会遇见一个很特别的人
          </p>
        </div>

        {/* CTA Button - premium feel */}
        <button
          onClick={onComplete}
          className={`mt-20 group relative overflow-hidden transition-all duration-700 ${
            stage !== 'cta' ? 'opacity-0 translate-y-10' : 'opacity-100 translate-y-0'
          }`}
        >
          {/* Button glow */}
          <div className="absolute inset-0 bg-gradient-to-r from-[#c8a888] via-[#d4b89a] to-[#c8a888] rounded-full blur-xl opacity-40 group-hover:opacity-60 transition-opacity" />
          
          {/* Button body */}
          <div className="relative px-14 py-4.5 bg-gradient-to-r from-[#c8a888] to-[#b89878] rounded-full text-[#1a1714] font-medium tracking-wide shadow-xl group-hover:shadow-2xl transition-all group-hover:scale-[1.02] active:scale-[0.98]">
            开始遇见
          </div>
        </button>

        {/* Bottom decorative element */}
        <div 
          className={`absolute bottom-16 left-1/2 -translate-x-1/2 flex items-center gap-4 transition-all duration-1000 delay-700 ${
            stage !== 'cta' ? 'opacity-0' : 'opacity-100'
          }`}
        >
          <div className="w-12 h-px bg-gradient-to-r from-transparent via-[#a09080]/50 to-transparent" />
          <span className="text-[10px] text-[#807060] tracking-[0.25em] uppercase font-light">认真恋爱</span>
          <div className="w-12 h-px bg-gradient-to-r from-transparent via-[#a09080]/50 to-transparent" />
        </div>
      </div>
    </div>
  )
}
