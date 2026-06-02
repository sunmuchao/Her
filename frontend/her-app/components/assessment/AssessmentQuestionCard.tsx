'use client'

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { ChevronLeft } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/hooks/use-reduced-motion'
import { type AssessmentType, getAssessmentTheme } from './assessment-themes'
import { 
  ParticleBurst, 
  RingBurst, 
  AnimatedCheck, 
  SelectionFlash,
  useHapticFeedback 
} from './immersive-effects'

interface QuestionData {
  current_question: number
  total_questions: number
  question_text: string
  options: Array<{ label: string; text: string; score: number }>
  progress: number
}

export function AssessmentQuestionCard({
  data,
  onAnswer,
  onPrevious,
  isSubmitting = false,
  assessmentType,
  onDimensionComplete,
}: {
  data: QuestionData
  onAnswer: (answer: string) => void
  onPrevious?: () => void
  isSubmitting?: boolean
  assessmentType?: AssessmentType
  onDimensionComplete?: (dimensionIndex: number) => void
}) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null)
  const [isAnimatingOut, setIsAnimatingOut] = useState(false)
  const [showParticles, setShowParticles] = useState(false)
  const [showFlash, setShowFlash] = useState(false)
  const [optionsAnimated, setOptionsAnimated] = useState(false)
  const prefersReducedMotion = useReducedMotion()
  const haptic = useHapticFeedback()
  const prevQuestionRef = useRef(data.current_question)
  
  const theme = getAssessmentTheme(assessmentType)
  const dimensions = theme.progressColors
  const questionsPerDimension = Math.ceil(data.total_questions / dimensions.length)

  // Calculate current dimension
  const currentDimensionIndex = Math.floor((data.current_question - 1) / questionsPerDimension)
  const questionInDimension = ((data.current_question - 1) % questionsPerDimension) + 1
  const currentDimension = dimensions[currentDimensionIndex]

  // Check if dimension will complete after this question
  const willCompleteDimension = questionInDimension === questionsPerDimension

  // Reset selection and trigger entrance animation when question changes
  useEffect(() => {
    if (data.current_question !== prevQuestionRef.current) {
      setSelectedOption(null)
      setIsAnimatingOut(false)
      setShowParticles(false)
      setOptionsAnimated(false)
      
      // Trigger staggered option entrance
      const timer = setTimeout(() => setOptionsAnimated(true), 50)
      prevQuestionRef.current = data.current_question
      return () => clearTimeout(timer)
    }
  }, [data.current_question])

  // Initial mount animation
  useEffect(() => {
    const timer = setTimeout(() => setOptionsAnimated(true), 100)
    return () => clearTimeout(timer)
  }, [])

  const handleOptionClick = useCallback((label: string) => {
    if (selectedOption || isSubmitting) return
    
    setSelectedOption(label)
    setShowParticles(true)
    
    // Enhanced haptic feedback
    if (!prefersReducedMotion) {
      haptic('success')
      setShowFlash(true)
    } else {
      haptic('light')
    }

    // Delay before submitting to show selection feedback
    const delay = prefersReducedMotion ? 100 : 500
    
    setTimeout(() => {
      setIsAnimatingOut(true)
      
      // Check for dimension completion
      if (willCompleteDimension) {
        onDimensionComplete?.(currentDimensionIndex)
      }
      
      setTimeout(() => {
        onAnswer(label)
      }, prefersReducedMotion ? 50 : 200)
    }, delay)
  }, [selectedOption, isSubmitting, prefersReducedMotion, onAnswer, haptic, willCompleteDimension, currentDimensionIndex, onDimensionComplete])

  // Keyboard navigation with arrow keys support
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (selectedOption || isSubmitting) return
      
      // Number/letter key mapping
      const keyMap: Record<string, string> = {
        '1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E',
        'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E',
      }
      
      const optionLabel = keyMap[e.key.toLowerCase()]
      if (optionLabel && data.options.find(o => o.label === optionLabel)) {
        handleOptionClick(optionLabel)
        return
      }
      
      // Arrow key navigation
      const focusedElement = document.activeElement as HTMLElement
      const optionButtons = Array.from(document.querySelectorAll('[role="option"]')) as HTMLElement[]
      const currentIndex = optionButtons.indexOf(focusedElement)
      
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault()
        const nextIndex = currentIndex < optionButtons.length - 1 ? currentIndex + 1 : 0
        optionButtons[nextIndex]?.focus()
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault()
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : optionButtons.length - 1
        optionButtons[prevIndex]?.focus()
      } else if (e.key === 'Enter' && focusedElement?.getAttribute('role') === 'option') {
        e.preventDefault()
        const label = focusedElement.getAttribute('data-label')
        if (label) handleOptionClick(label)
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [data.options, selectedOption, isSubmitting, handleOptionClick])

  // Memoized theme-specific colors
  const themeColors = useMemo(() => ({
    selectedBorder: assessmentType === 'attachment_style' ? 'border-coral' :
                    assessmentType === 'love_language' ? 'border-lavender' : 'border-primary',
    selectedBg: assessmentType === 'attachment_style' ? 'bg-coral/10' :
                assessmentType === 'love_language' ? 'bg-lavender/10' : 'bg-primary/10',
    selectedLabel: assessmentType === 'attachment_style' ? 'bg-coral text-white' :
                   assessmentType === 'love_language' ? 'bg-lavender text-white' : 'bg-primary text-primary-foreground',
    ripple: assessmentType === 'attachment_style' ? 'bg-coral/15' :
            assessmentType === 'love_language' ? 'bg-lavender/15' : 'bg-primary/15',
    focusRing: assessmentType === 'attachment_style' ? 'focus-visible:ring-coral' :
               assessmentType === 'love_language' ? 'focus-visible:ring-lavender' : 'focus-visible:ring-primary',
    particleColors: assessmentType === 'attachment_style' 
      ? ['var(--coral)', 'var(--rose)', 'var(--gold)']
      : assessmentType === 'love_language'
        ? ['var(--lavender)', 'var(--purple)', 'var(--rose)']
        : ['var(--primary)', 'var(--gold)', 'var(--rose)'],
    flashColor: assessmentType === 'attachment_style' ? 'var(--coral)' :
                assessmentType === 'love_language' ? 'var(--lavender)' : 'var(--primary)',
    glow: assessmentType === 'attachment_style' ? 'glow-coral' :
          assessmentType === 'love_language' ? 'glow-lavender' : 'glow-primary',
  }), [assessmentType])

  // Memoized progress bar segments
  const progressSegments = useMemo(() => {
    return dimensions.map((dim, idx) => {
      const segmentSize = 100 / dimensions.length
      const segmentStart = idx * segmentSize
      const segmentEnd = (idx + 1) * segmentSize
      const segmentProgress = Math.min(100, Math.max(0, (data.progress - segmentStart) / segmentSize * 100))
      const isActive = idx === currentDimensionIndex
      const isCompleted = data.progress >= segmentEnd
      
      return { dim, segmentProgress, isActive, isCompleted }
    })
  }, [dimensions, data.progress, currentDimensionIndex])

  return (
    <>
      {/* Selection Flash Overlay */}
      <SelectionFlash trigger={showFlash} color={themeColors.flashColor} />
      
      <div className={cn(
        'rounded-3xl border border-border bg-card p-5 shadow-sm will-change-transform perspective-1000',
        isAnimatingOut ? 'animate-slide-scale-out' : 'animate-slide-scale-in'
      )}>
        {/* Header with back button and progress */}
        <div className="flex items-center gap-3 mb-4">
          {onPrevious ? (
            <button
              onClick={onPrevious}
              className="flex items-center justify-center w-8 h-8 rounded-full bg-secondary hover:bg-secondary/80 transition-colors touch-target"
              aria-label="返回上一题"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          ) : (
            <div className="w-8" />
          )}
          
          <div className="flex-1">
            {/* Question counter with animated number */}
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
              <span className="flex items-center gap-1.5">
                <span className={cn(
                  'inline-block w-2 h-2 rounded-full transition-all duration-300',
                  currentDimension?.color || 'bg-primary',
                  selectedOption && 'animate-pulse-soft'
                )} />
                {currentDimension?.name || '测评'}
                {' '}<span className="tabular-nums">{questionInDimension}</span>/{questionsPerDimension}
              </span>
              <span className="tabular-nums font-medium">
                <span className={cn(selectedOption && 'animate-number-roll inline-block')}>
                  {data.current_question}
                </span>
                /{data.total_questions}
              </span>
            </div>
            
            {/* Segmented Progress Bar with glow */}
            <div className="flex gap-0.5 sm:gap-1" role="progressbar" aria-valuenow={data.progress} aria-valuemin={0} aria-valuemax={100}>
              {progressSegments.map(({ dim, segmentProgress, isActive, isCompleted }) => (
                <div
                  key={dim.key}
                  className={cn(
                    'flex-1 h-1.5 sm:h-2 rounded-full overflow-hidden transition-all duration-300',
                    isActive ? 'bg-secondary ring-1 ring-border' : 'bg-secondary/60'
                  )}
                  title={dim.name}
                >
                  <div
                    className={cn(
                      'h-full rounded-full transition-all duration-500 ease-out',
                      isCompleted ? dim.color : isActive ? dim.color : 'bg-transparent',
                      isActive && segmentProgress > 90 && !prefersReducedMotion && 'animate-progress-glow'
                    )}
                    style={{ width: isCompleted ? '100%' : isActive ? `${segmentProgress}%` : '0%' }}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Question Text */}
        <h3 className="text-lg font-semibold leading-snug text-balance animate-fade-in">
          {data.question_text}
        </h3>

        {/* Options with staggered entrance and burst effects */}
        <div className="mt-5 grid gap-2.5" role="listbox" aria-label="选择答案">
          {data.options.map((option, index) => {
            const isSelected = selectedOption === option.label
            const isDisabled = selectedOption !== null || isSubmitting
            
            return (
              <button
                key={option.label}
                onClick={() => handleOptionClick(option.label)}
                disabled={isDisabled}
                role="option"
                data-label={option.label}
                aria-selected={isSelected}
                aria-label={`选项 ${option.label}: ${option.text}`}
                className={cn(
                  'relative flex items-start gap-3 w-full text-left rounded-2xl border p-4',
                  'transition-all touch-target',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
                  themeColors.focusRing,
                  isSelected
                    ? cn(
                        themeColors.selectedBorder, 
                        themeColors.selectedBg, 
                        'border-2',
                        !prefersReducedMotion && 'animate-elastic-pop'
                      )
                    : 'border-border bg-background hover:border-border/80 hover:bg-secondary/30 active:bg-secondary/50',
                  isDisabled && !isSelected && 'opacity-40 cursor-not-allowed',
                  !prefersReducedMotion && !isDisabled && 'hover:scale-[1.01] active:scale-[0.99]',
                  // Staggered entrance animation
                  optionsAnimated ? 'animate-option-entrance' : 'opacity-0 translate-y-4'
                )}
                style={{
                  animationDelay: optionsAnimated ? `${index * 60}ms` : undefined,
                }}
              >
                {/* Particle burst on selection */}
                {isSelected && !prefersReducedMotion && (
                  <ParticleBurst 
                    trigger={showParticles} 
                    colors={themeColors.particleColors}
                    particleCount={16}
                  />
                )}
                
                {/* Ring burst on selection */}
                {isSelected && !prefersReducedMotion && (
                  <RingBurst 
                    trigger={showParticles} 
                    color={themeColors.flashColor}
                    rings={2}
                  />
                )}

                {/* Option Label Circle with animated check */}
                <span
                  className={cn(
                    'relative flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold shrink-0 transition-all duration-300',
                    isSelected
                      ? cn(themeColors.selectedLabel, !prefersReducedMotion && 'scale-110')
                      : 'bg-secondary text-secondary-foreground'
                  )}
                >
                  {isSelected ? (
                    <AnimatedCheck show={true} size={18} color="currentColor" />
                  ) : (
                    option.label
                  )}
                </span>
                
                {/* Option Text */}
                <span className={cn(
                  'flex-1 text-sm leading-relaxed pt-1 transition-colors duration-200',
                  isSelected && 'font-medium'
                )}>
                  {option.text}
                </span>

                {/* Shimmer effect on hover */}
                {!isDisabled && !prefersReducedMotion && (
                  <span className="absolute inset-0 rounded-2xl overflow-hidden pointer-events-none">
                    <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/10 to-transparent group-hover:animate-shimmer-sweep" />
                  </span>
                )}
              </button>
            )
          })}
        </div>

        {/* Keyboard hint - hidden on mobile */}
        <p className="mt-4 text-center text-xs text-muted-foreground hidden sm:block animate-fade-in" style={{ animationDelay: '300ms' }}>
          <span className="sr-only">{"键盘快捷键: "}</span>
          <span aria-hidden="true">{"按 1-5 数字键快速选择，方向键导航，Enter 确认"}</span>
        </p>
      </div>
    </>
  )
}
