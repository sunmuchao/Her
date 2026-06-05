'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { cn } from '@/lib/utils'
import { type AssessmentType } from './assessment-themes'

// ============================================
// PARTICLE BURST EFFECT
// ============================================

interface Particle {
  id: number
  x: number
  y: number
  angle: number
  speed: number
  size: number
  color: string
  delay: number
}

export function ParticleBurst({
  trigger,
  colors = ['var(--primary)', 'var(--gold)', 'var(--rose)'],
  particleCount = 12,
  className,
}: {
  trigger: boolean
  colors?: string[]
  particleCount?: number
  className?: string
}) {
  const [particles, setParticles] = useState<Particle[]>([])
  
  useEffect(() => {
    if (trigger) {
      const newParticles: Particle[] = []
      for (let i = 0; i < particleCount; i++) {
        newParticles.push({
          id: i,
          x: 50,
          y: 50,
          angle: (360 / particleCount) * i + Math.random() * 30,
          speed: 50 + Math.random() * 50,
          size: 4 + Math.random() * 6,
          color: colors[Math.floor(Math.random() * colors.length)],
          delay: Math.random() * 100,
        })
      }
      setParticles(newParticles)
      
      // Clear particles after animation
      const timer = setTimeout(() => setParticles([]), 800)
      return () => clearTimeout(timer)
    }
  }, [trigger, colors, particleCount])
  
  if (particles.length === 0) return null
  
  return (
    <div className={cn('absolute inset-0 pointer-events-none overflow-hidden z-20', className)}>
      {particles.map((p) => {
        const rad = (p.angle * Math.PI) / 180
        const moveX = Math.cos(rad) * p.speed
        const moveY = Math.sin(rad) * p.speed
        
        return (
          <div
            key={p.id}
            className="absolute rounded-full animate-particle-burst"
            style={{
              left: `${p.x}%`,
              top: `${p.y}%`,
              width: p.size,
              height: p.size,
              backgroundColor: p.color,
              '--particle-x': `${moveX}px`,
              '--particle-y': `${moveY}px`,
              animationDelay: `${p.delay}ms`,
              animationDuration: '600ms',
            } as React.CSSProperties}
          />
        )
      })}
    </div>
  )
}

// ============================================
// RING BURST EFFECT
// ============================================

export function RingBurst({
  trigger,
  color = 'var(--primary)',
  rings = 3,
  className,
}: {
  trigger: boolean
  color?: string
  rings?: number
  className?: string
}) {
  const [active, setActive] = useState(false)
  
  useEffect(() => {
    if (trigger) {
      setActive(true)
      const timer = setTimeout(() => setActive(false), 600)
      return () => clearTimeout(timer)
    }
  }, [trigger])
  
  if (!active) return null
  
  return (
    <div className={cn('absolute inset-0 pointer-events-none flex items-center justify-center', className)}>
      {Array.from({ length: rings }).map((_, i) => (
        <div
          key={i}
          className="absolute rounded-full border-2 animate-ring-burst"
          style={{
            width: '100%',
            height: '100%',
            borderColor: color,
            animationDelay: `${i * 100}ms`,
          }}
        />
      ))}
    </div>
  )
}

// ============================================
// ANIMATED CHECK MARK
// ============================================

export function AnimatedCheck({
  show,
  color = 'currentColor',
  size = 16,
  className,
}: {
  show: boolean
  color?: string
  size?: number
  className?: string
}) {
  if (!show) return null
  
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={cn('animate-check-draw', className)}
      style={{ color }}
    >
      <path
        d="M5 12l5 5L19 7"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ============================================
// NUMBER COUNTER ANIMATION
// ============================================

export function AnimatedNumber({
  value,
  duration = 1000,
  className,
  suffix = '',
  decimals = 0,
}: {
  value: number
  duration?: number
  className?: string
  suffix?: string
  decimals?: number
}) {
  const [displayValue, setDisplayValue] = useState(0)
  const startTime = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)
  
  useEffect(() => {
    const startValue = displayValue
    const diff = value - startValue
    
    const animate = (timestamp: number) => {
      if (startTime.current === null) {
        startTime.current = timestamp
      }
      
      const elapsed = timestamp - startTime.current
      const progress = Math.min(elapsed / duration, 1)
      
      // Easing function (ease-out cubic)
      const eased = 1 - Math.pow(1 - progress, 3)
      
      const current = startValue + diff * eased
      setDisplayValue(current)
      
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }
    
    startTime.current = null
    rafRef.current = requestAnimationFrame(animate)
    
    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
      }
    }
  }, [value, duration])
  
  return (
    <span className={cn('tabular-nums', className)}>
      {displayValue.toFixed(decimals)}{suffix}
    </span>
  )
}

// ============================================
// CONFETTI CELEBRATION
// ============================================

interface ConfettiPiece {
  id: number
  x: number
  color: string
  delay: number
  duration: number
  rotation: number
}

export function ConfettiCelebration({
  trigger,
  colors,
  pieceCount = 50,
}: {
  trigger: boolean
  colors?: string[]
  pieceCount?: number
}) {
  const [pieces, setPieces] = useState<ConfettiPiece[]>([])

  useEffect(() => {
    if (trigger) {
      const defaultColors = ['var(--primary)', 'var(--gold)', 'var(--rose)', 'var(--coral)', 'var(--lavender)']
      const usedColors = colors || defaultColors

      const newPieces: ConfettiPiece[] = []
      for (let i = 0; i < pieceCount; i++) {
        newPieces.push({
          id: i,
          x: Math.random() * 100,
          color: usedColors[Math.floor(Math.random() * usedColors.length)],
          delay: Math.random() * 500,
          duration: 2000 + Math.random() * 1000,
          rotation: Math.random() * 360,
        })
      }
      setPieces(newPieces)

      const timer = setTimeout(() => setPieces([]), 3500)
      return () => clearTimeout(timer)
    }
  }, [trigger, pieceCount, colors])  // 只依赖 props，colors 是稳定的

  if (pieces.length === 0) return null
  
  return (
    <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden">
      {pieces.map((piece) => (
        <div
          key={piece.id}
          className="absolute w-3 h-3 animate-confetti-fall"
          style={{
            left: `${piece.x}%`,
            top: '-20px',
            backgroundColor: piece.color,
            borderRadius: Math.random() > 0.5 ? '50%' : '2px',
            animationDelay: `${piece.delay}ms`,
            animationDuration: `${piece.duration}ms`,
            transform: `rotate(${piece.rotation}deg)`,
          }}
        />
      ))}
    </div>
  )
}

// ============================================
// MILESTONE CELEBRATION OVERLAY
// ============================================

export function MilestoneCelebration({
  show,
  title,
  subtitle,
  assessmentType,
  onComplete,
}: {
  show: boolean
  title: string
  subtitle?: string
  assessmentType?: AssessmentType
  onComplete?: () => void
}) {
  useEffect(() => {
    if (show && onComplete) {
      const timer = setTimeout(onComplete, 2000)
      return () => clearTimeout(timer)
    }
  }, [show, onComplete])
  
  if (!show) return null
  
  const bgColor = assessmentType === 'attachment_style' ? 'bg-coral' : 'bg-primary'
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
      {/* Background flash */}
      <div className={cn('absolute inset-0 animate-selection-flash', bgColor)} />
      
      {/* Burst rings */}
      <div className="absolute">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className={cn('absolute w-32 h-32 rounded-full border-4 animate-milestone-burst', 
              assessmentType === 'attachment_style' ? 'border-coral' :
              'border-primary'
            )}
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
      
      {/* Content */}
      <div className="relative animate-dimension-complete text-center">
        <div className={cn(
          'text-4xl font-bold mb-2',
          assessmentType === 'attachment_style' ? 'text-coral' :
          'text-primary'
        )}>
          {title}
        </div>
        {subtitle && (
          <div className="text-lg text-muted-foreground">{subtitle}</div>
        )}
      </div>
    </div>
  )
}

// ============================================
// SELECTION FLASH OVERLAY
// ============================================

export function SelectionFlash({
  trigger,
  color = 'var(--primary)',
}: {
  trigger: boolean
  color?: string
}) {
  const [active, setActive] = useState(false)
  
  useEffect(() => {
    if (trigger) {
      setActive(true)
      const timer = setTimeout(() => setActive(false), 400)
      return () => clearTimeout(timer)
    }
  }, [trigger])
  
  if (!active) return null
  
  return (
    <div 
      className="fixed inset-0 pointer-events-none z-40 animate-selection-flash"
      style={{ backgroundColor: color }}
    />
  )
}

// ============================================
// AMBIENT BACKGROUND
// ============================================

export function AmbientBackground({
  assessmentType,
  progress = 0,
  className,
}: {
  assessmentType?: AssessmentType
  progress?: number
  className?: string
}) {
  const getGradient = useCallback(() => {
    const intensity = 0.1 + (progress / 100) * 0.15
    
    switch (assessmentType) {
      case 'attachment_style':
        return `radial-gradient(ellipse at 30% 20%, rgba(var(--coral), ${intensity}) 0%, transparent 50%),
                radial-gradient(ellipse at 70% 80%, rgba(var(--coral), ${intensity * 0.5}) 0%, transparent 40%)`
      default:
        return `radial-gradient(ellipse at 30% 20%, rgba(var(--primary), ${intensity}) 0%, transparent 50%),
                radial-gradient(ellipse at 70% 80%, rgba(var(--rose), ${intensity * 0.5}) 0%, transparent 40%)`
    }
  }, [assessmentType, progress])
  
  return (
    <div 
      className={cn('fixed inset-0 pointer-events-none transition-all duration-1000', className)}
      style={{ background: getGradient() }}
    />
  )
}

// ============================================
// PROGRESS MILESTONE INDICATOR
// ============================================

export function ProgressMilestone({
  progress,
  milestones = [25, 50, 75, 100],
  assessmentType,
  onMilestoneReached,
}: {
  progress: number
  milestones?: number[]
  assessmentType?: AssessmentType
  onMilestoneReached?: (milestone: number) => void
}) {
  const reachedMilestonesRef = useRef<Set<number>>(new Set())
  
  useEffect(() => {
    for (const milestone of milestones) {
      if (progress >= milestone && !reachedMilestonesRef.current.has(milestone)) {
        reachedMilestonesRef.current.add(milestone)
        onMilestoneReached?.(milestone)
      }
    }
  }, [progress, milestones, onMilestoneReached])
  
  const color = assessmentType === 'attachment_style' ? 'bg-coral' : 'bg-primary'
  
  return (
    <div className="relative h-2 bg-secondary rounded-full overflow-hidden">
      {/* Progress fill */}
      <div 
        className={cn('h-full rounded-full transition-all duration-500', color)}
        style={{ width: `${progress}%` }}
      />
      
      {/* Milestone markers */}
      {milestones.slice(0, -1).map((milestone) => (
        <div
          key={milestone}
          className={cn(
            'absolute top-1/2 -translate-y-1/2 w-1 h-3 rounded-full transition-colors duration-300',
            progress >= milestone ? 'bg-background' : 'bg-muted-foreground/30'
          )}
          style={{ left: `${milestone}%` }}
        />
      ))}
      
      {/* Glow effect when near milestone */}
      {milestones.some(m => progress >= m - 5 && progress < m) && (
        <div className={cn('absolute inset-0 animate-progress-glow', color)} />
      )}
    </div>
  )
}

// ============================================
// HAPTIC FEEDBACK HELPER
// ============================================

export function useHapticFeedback() {
  return useCallback((type: 'light' | 'medium' | 'heavy' | 'success' | 'error') => {
    if (!navigator.vibrate) return
    
    switch (type) {
      case 'light':
        navigator.vibrate(10)
        break
      case 'medium':
        navigator.vibrate(25)
        break
      case 'heavy':
        navigator.vibrate(50)
        break
      case 'success':
        navigator.vibrate([10, 50, 30])
        break
      case 'error':
        navigator.vibrate([50, 30, 50])
        break
    }
  }, [])
}

// ============================================
// SCORE REVEAL ANIMATION
// ============================================

export function ScoreReveal({
  score,
  maxScore = 100,
  assessmentType,
  onRevealComplete,
}: {
  score: number
  maxScore?: number
  assessmentType?: AssessmentType
  onRevealComplete?: () => void
}) {
  const [revealed, setRevealed] = useState(false)
  const [displayScore, setDisplayScore] = useState(0)
  
  useEffect(() => {
    // Start reveal animation
    const revealTimer = setTimeout(() => setRevealed(true), 100)
    
    // Animate score counting
    const duration = 1500
    const startTime = Date.now()
    
    const countUp = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      
      setDisplayScore(Math.round(score * eased))
      
      if (progress < 1) {
        requestAnimationFrame(countUp)
      } else {
        onRevealComplete?.()
      }
    }
    
    const countTimer = setTimeout(() => requestAnimationFrame(countUp), 500)
    
    return () => {
      clearTimeout(revealTimer)
      clearTimeout(countTimer)
    }
  }, [score, onRevealComplete])
  
  const color = assessmentType === 'attachment_style' ? 'text-coral' : 'text-primary'
  
  return (
    <div className={cn(
      'text-center transition-all duration-500',
      revealed ? 'animate-score-reveal' : 'opacity-0 scale-50 blur-lg'
    )}>
      <div className={cn('text-6xl font-bold tabular-nums', color)}>
        {displayScore}
      </div>
      <div className="text-lg text-muted-foreground mt-2">
        / {maxScore} 分
      </div>
    </div>
  )
}
