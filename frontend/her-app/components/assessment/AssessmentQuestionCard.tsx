'use client'

import { useState, useCallback, useEffect, useMemo } from 'react'
import { ChevronLeft, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/hooks/use-reduced-motion'
import { type AssessmentType, getAssessmentTheme } from './assessment-themes'

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
  onDimensionComplete: _onDimensionComplete,
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
  const prefersReducedMotion = useReducedMotion()
  
  const theme = getAssessmentTheme(assessmentType)
  const dimensions = theme.progressColors
  const questionsPerDimension = Math.ceil(data.total_questions / dimensions.length)

  // Calculate current dimension
  const currentDimensionIndex = Math.floor((data.current_question - 1) / questionsPerDimension)
  const questionInDimension = ((data.current_question - 1) % questionsPerDimension) + 1
  const currentDimension = dimensions[currentDimensionIndex]

  // Reset selection when question changes
  useEffect(() => {
    setSelectedOption(null)
    setIsAnimatingOut(false)
  }, [data.current_question])

  const handleOptionClick = useCallback((label: string) => {
    if (selectedOption || isSubmitting) return
    
    setSelectedOption(label)
    
    // Haptic feedback if available
    if (navigator.vibrate) {
      navigator.vibrate(10)
    }

    // Delay before submitting to show selection feedback
    const delay = prefersReducedMotion ? 100 : 350
    
    setTimeout(() => {
      setIsAnimatingOut(true)
      setTimeout(() => {
        onAnswer(label)
      }, prefersReducedMotion ? 50 : 150)
    }, delay)
  }, [selectedOption, isSubmitting, prefersReducedMotion, onAnswer])

  // Keyboard navigation with arrow keys support
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (selectedOption || isSubmitting) return
      
      // Number/letter key mapping
      const keyMap: Record<string, string> = {}
      data.options.forEach((option, index) => {
        const numberKey = String(index + 1)
        const letterKey = String.fromCharCode(97 + index)
        keyMap[numberKey] = option.label
        keyMap[letterKey] = option.label
      })
      
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
    selectedBorder:
      assessmentType === 'attachment_style'
        ? 'border-coral'
        : assessmentType === 'big_five'
          ? 'border-sage'
          : assessmentType === 'sternberg_triangular_love'
            ? 'border-amber'
            : 'border-primary',
    selectedBg:
      assessmentType === 'attachment_style'
        ? 'bg-coral/5'
        : assessmentType === 'big_five'
          ? 'bg-sage/5'
          : assessmentType === 'sternberg_triangular_love'
            ? 'bg-amber/5'
            : 'bg-primary/5',
    selectedLabel:
      assessmentType === 'attachment_style'
        ? 'bg-coral text-white'
        : assessmentType === 'big_five'
          ? 'bg-sage text-white'
          : assessmentType === 'sternberg_triangular_love'
            ? 'bg-amber text-white'
            : 'bg-primary text-primary-foreground',
    ripple:
      assessmentType === 'attachment_style'
        ? 'bg-coral/10'
        : assessmentType === 'big_five'
          ? 'bg-sage/10'
          : assessmentType === 'sternberg_triangular_love'
            ? 'bg-amber/10'
            : 'bg-primary/10',
    focusRing:
      assessmentType === 'attachment_style'
        ? 'focus-visible:ring-coral'
        : assessmentType === 'big_five'
          ? 'focus-visible:ring-sage'
          : assessmentType === 'sternberg_triangular_love'
            ? 'focus-visible:ring-amber'
            : 'focus-visible:ring-primary',
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
    <div className={cn(
      'rounded-3xl border border-border bg-card p-5 shadow-sm will-change-transform',
      isAnimatingOut ? 'animate-fade-out' : 'animate-fade-in-up'
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
          {/* Question counter */}
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span className="flex items-center gap-1.5">
              <span className={cn(
                'inline-block w-2 h-2 rounded-full',
                currentDimension?.color || 'bg-primary'
              )} />
              {currentDimension?.name || '测评'}
              {' '}{questionInDimension}/{questionsPerDimension}
            </span>
            <span>{data.current_question}/{data.total_questions}</span>
          </div>
          
          {/* Segmented Progress Bar - Mobile optimized */}
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
                    isCompleted ? dim.color : isActive ? dim.color : 'bg-transparent'
                  )}
                  style={{ width: isCompleted ? '100%' : isActive ? `${segmentProgress}%` : '0%' }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Question Text */}
      <h3 className="text-lg font-semibold leading-snug text-balance">
        {data.question_text}
      </h3>

      {/* Options */}
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
                'transition-all duration-200 touch-target',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
                themeColors.focusRing,
                isSelected
                  ? cn(themeColors.selectedBorder, themeColors.selectedBg, 'scale-[1.02]')
                  : 'border-border bg-background hover:border-border/80 hover:bg-secondary/30 active:bg-secondary/50',
                isDisabled && !isSelected && 'opacity-50 cursor-not-allowed',
                !prefersReducedMotion && 'active:scale-[0.98]'
              )}
              style={{
                animationDelay: `${index * 50}ms`,
              }}
            >
              {/* Option Label Circle */}
              <span
                className={cn(
                  'flex items-center justify-center w-7 h-7 rounded-full text-xs font-medium shrink-0 transition-all duration-200',
                  isSelected
                    ? themeColors.selectedLabel
                    : 'bg-secondary text-secondary-foreground'
                )}
              >
                {isSelected ? <Check className="w-4 h-4" /> : option.label}
              </span>
              
              {/* Option Text */}
              <span className="flex-1 text-sm leading-relaxed pt-0.5">
                {option.text}
              </span>

              {/* Selection ripple effect */}
              {isSelected && !prefersReducedMotion && (
                <span className={cn('absolute inset-0 rounded-2xl animate-scale-in', themeColors.ripple)} />
              )}
            </button>
          )
        })}
      </div>

      {/* Keyboard hint - hidden on mobile */}
      <p className="mt-4 text-center text-xs text-muted-foreground hidden sm:block">
        <span className="sr-only">{"键盘快捷键: "}</span>
        <span aria-hidden="true">{`按 1-${data.options.length} 数字键快速选择，方向键导航，Enter 确认`}</span>
      </p>
    </div>
  )
}
