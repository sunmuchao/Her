'use client'

import { useState, useCallback, useEffect } from 'react'
import { ChevronLeft, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useReducedMotion } from '@/hooks/use-reduced-motion'

interface QuestionData {
  current_question: number
  total_questions: number
  question_text: string
  options: Array<{ label: string; text: string; score: number }>
  progress: number
}

// MBTI dimension info for segmented progress
const DIMENSIONS = [
  { key: 'EI', name: '社交能量', color: 'bg-rose' },
  { key: 'SN', name: '信息感知', color: 'bg-gold' },
  { key: 'TF', name: '决策方式', color: 'bg-primary' },
  { key: 'JP', name: '生活态度', color: 'bg-taupe' },
]

export function AssessmentQuestionCard({
  data,
  onAnswer,
  onPrevious,
  isSubmitting = false,
}: {
  data: QuestionData
  onAnswer: (answer: string) => void
  onPrevious?: () => void
  isSubmitting?: boolean
}) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null)
  const [isAnimatingOut, setIsAnimatingOut] = useState(false)
  const prefersReducedMotion = useReducedMotion()

  // Calculate current dimension (5 questions per dimension)
  const currentDimensionIndex = Math.floor((data.current_question - 1) / 5)
  const questionInDimension = ((data.current_question - 1) % 5) + 1
  const currentDimension = DIMENSIONS[currentDimensionIndex]

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

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (selectedOption || isSubmitting) return
      
      const keyMap: Record<string, string> = {
        '1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E',
        'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E',
      }
      
      const optionLabel = keyMap[e.key.toLowerCase()]
      if (optionLabel && data.options.find(o => o.label === optionLabel)) {
        handleOptionClick(optionLabel)
      }
    }
    
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [data.options, selectedOption, isSubmitting, handleOptionClick])

  return (
    <div className={cn(
      'rounded-3xl border border-border bg-card p-5 shadow-sm',
      isAnimatingOut ? 'animate-fade-out' : 'animate-fade-in-up'
    )}>
      {/* Header with back button and progress */}
      <div className="flex items-center gap-3 mb-4">
        {onPrevious ? (
          <button
            onClick={onPrevious}
            className="flex items-center justify-center w-8 h-8 rounded-full bg-secondary hover:bg-secondary/80 transition-colors"
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
              {' '}{questionInDimension}/5
            </span>
            <span>{data.current_question}/{data.total_questions}</span>
          </div>
          
          {/* Segmented Progress Bar */}
          <div className="flex gap-1" role="progressbar" aria-valuenow={data.progress} aria-valuemin={0} aria-valuemax={100}>
            {DIMENSIONS.map((dim, idx) => {
              const segmentStart = idx * 25
              const segmentEnd = (idx + 1) * 25
              const segmentProgress = Math.min(100, Math.max(0, (data.progress - segmentStart) / 25 * 100))
              const isActive = idx === currentDimensionIndex
              const isCompleted = data.progress >= segmentEnd
              
              return (
                <div
                  key={dim.key}
                  className={cn(
                    'flex-1 h-2 rounded-full overflow-hidden transition-all duration-300',
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
              )
            })}
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
              aria-selected={isSelected}
              aria-label={`选项 ${option.label}: ${option.text}`}
              className={cn(
                'relative flex items-start gap-3 w-full text-left rounded-2xl border p-4 transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
                isSelected
                  ? 'border-primary bg-primary/5 scale-[1.02]'
                  : 'border-border bg-background hover:border-primary/30 hover:bg-secondary/30',
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
                    ? 'bg-primary text-primary-foreground'
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
                <span className="absolute inset-0 rounded-2xl bg-primary/10 animate-scale-in" />
              )}
            </button>
          )
        })}
      </div>

      {/* Keyboard hint */}
      <p className="mt-4 text-center text-xs text-muted-foreground">
        <span className="sr-only">{"键盘快捷键: "}</span>
        <span aria-hidden="true">{"按 1-5 数字键可快速选择"}</span>
      </p>
    </div>
  )
}
