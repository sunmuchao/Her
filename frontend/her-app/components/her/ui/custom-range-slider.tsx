'use client'

import { useState, useRef, useCallback } from 'react'
import { cn } from '@/lib/utils'

interface CustomRangeSliderProps {
  min: number
  max: number
  value: [number, number]
  onChange: (value: [number, number]) => void
  step?: number
  className?: string
  showLabels?: boolean
  formatLabel?: (value: number) => string
}

export function CustomRangeSlider({
  min,
  max,
  value,
  onChange,
  step = 1,
  className,
  showLabels = true,
  formatLabel = (v) => String(v)
}: CustomRangeSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [activeThumb, setActiveThumb] = useState<'start' | 'end' | null>(null)

  const getPercentage = (val: number) => ((val - min) / (max - min)) * 100
  const getValue = (percentage: number) => {
    const rawValue = (percentage / 100) * (max - min) + min
    return Math.round(rawValue / step) * step
  }

  const handleMove = useCallback((clientX: number) => {
    if (!trackRef.current || !activeThumb) return

    const rect = trackRef.current.getBoundingClientRect()
    const percentage = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
    const newValue = getValue(percentage)

    if (activeThumb === 'start') {
      onChange([Math.min(newValue, value[1] - step), value[1]])
    } else {
      onChange([value[0], Math.max(newValue, value[0] + step)])
    }
  }, [activeThumb, value, onChange, min, max, step])

  const handleMouseMove = useCallback((e: MouseEvent) => {
    handleMove(e.clientX)
  }, [handleMove])

  const handleTouchMove = useCallback((e: TouchEvent) => {
    handleMove(e.touches[0].clientX)
  }, [handleMove])

  const handleEnd = useCallback(() => {
    setActiveThumb(null)
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleEnd)
    document.removeEventListener('touchmove', handleTouchMove)
    document.removeEventListener('touchend', handleEnd)
  }, [handleMouseMove, handleTouchMove])

  const handleStart = useCallback((thumb: 'start' | 'end') => {
    setActiveThumb(thumb)
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleEnd)
    document.addEventListener('touchmove', handleTouchMove)
    document.addEventListener('touchend', handleEnd)
  }, [handleMouseMove, handleEnd, handleTouchMove])

  const startPercent = getPercentage(value[0])
  const endPercent = getPercentage(value[1])

  return (
    <div className={cn('w-full', className)}>
      {showLabels && (
        <div className="flex justify-between mb-2">
          <span className="text-sm font-medium text-foreground">{formatLabel(value[0])}</span>
          <span className="text-sm font-medium text-foreground">{formatLabel(value[1])}</span>
        </div>
      )}
      
      <div className="relative h-10 flex items-center">
        {/* Track background */}
        <div
          ref={trackRef}
          className="absolute w-full h-2 bg-secondary rounded-full"
        >
          {/* Active track */}
          <div
            className="absolute h-full bg-primary rounded-full transition-all"
            style={{
              left: `${startPercent}%`,
              width: `${endPercent - startPercent}%`
            }}
          />
        </div>

        {/* Start thumb */}
        <button
          type="button"
          className={cn(
            'absolute w-6 h-6 bg-card border-2 border-primary rounded-full shadow-md',
            'transform -translate-x-1/2 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
            activeThumb === 'start' && 'scale-110'
          )}
          style={{ left: `${startPercent}%` }}
          onMouseDown={() => handleStart('start')}
          onTouchStart={() => handleStart('start')}
          aria-label={`最小值: ${formatLabel(value[0])}`}
          aria-valuemin={min}
          aria-valuemax={value[1]}
          aria-valuenow={value[0]}
          role="slider"
        />

        {/* End thumb */}
        <button
          type="button"
          className={cn(
            'absolute w-6 h-6 bg-card border-2 border-primary rounded-full shadow-md',
            'transform -translate-x-1/2 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
            activeThumb === 'end' && 'scale-110'
          )}
          style={{ left: `${endPercent}%` }}
          onMouseDown={() => handleStart('end')}
          onTouchStart={() => handleStart('end')}
          aria-label={`最大值: ${formatLabel(value[1])}`}
          aria-valuemin={value[0]}
          aria-valuemax={max}
          aria-valuenow={value[1]}
          role="slider"
        />
      </div>

      {/* Min/Max labels */}
      <div className="flex justify-between mt-1">
        <span className="text-xs text-muted-foreground">{formatLabel(min)}</span>
        <span className="text-xs text-muted-foreground">{formatLabel(max)}</span>
      </div>
    </div>
  )
}

// Single value slider
interface SingleSliderProps {
  min: number
  max: number
  value: number
  onChange: (value: number) => void
  step?: number
  className?: string
  showLabel?: boolean
  formatLabel?: (value: number) => string
}

export function SingleSlider({
  min,
  max,
  value,
  onChange,
  step = 1,
  className,
  showLabel = true,
  formatLabel = (v) => String(v)
}: SingleSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  const percentage = ((value - min) / (max - min)) * 100

  const handleMove = useCallback((clientX: number) => {
    if (!trackRef.current) return

    const rect = trackRef.current.getBoundingClientRect()
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
    const rawValue = (pct / 100) * (max - min) + min
    const snappedValue = Math.round(rawValue / step) * step
    onChange(Math.max(min, Math.min(max, snappedValue)))
  }, [min, max, step, onChange])

  const handleMouseMove = useCallback((e: MouseEvent) => handleMove(e.clientX), [handleMove])
  const handleTouchMove = useCallback((e: TouchEvent) => handleMove(e.touches[0].clientX), [handleMove])

  const handleEnd = useCallback(() => {
    setIsDragging(false)
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleEnd)
    document.removeEventListener('touchmove', handleTouchMove)
    document.removeEventListener('touchend', handleEnd)
  }, [handleMouseMove, handleTouchMove])

  const handleStart = useCallback(() => {
    setIsDragging(true)
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleEnd)
    document.addEventListener('touchmove', handleTouchMove)
    document.addEventListener('touchend', handleEnd)
  }, [handleMouseMove, handleEnd, handleTouchMove])

  return (
    <div className={cn('w-full', className)}>
      {showLabel && (
        <div className="flex justify-center mb-2">
          <span className="text-lg font-semibold text-foreground">{formatLabel(value)}</span>
        </div>
      )}
      
      <div className="relative h-10 flex items-center">
        <div ref={trackRef} className="absolute w-full h-2 bg-secondary rounded-full">
          <div
            className="absolute h-full bg-primary rounded-full transition-all"
            style={{ width: `${percentage}%` }}
          />
        </div>

        <button
          type="button"
          className={cn(
            'absolute w-7 h-7 bg-card border-2 border-primary rounded-full shadow-lg',
            'transform -translate-x-1/2 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-primary',
            isDragging && 'scale-110'
          )}
          style={{ left: `${percentage}%` }}
          onMouseDown={handleStart}
          onTouchStart={handleStart}
          aria-label={formatLabel(value)}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          role="slider"
        />
      </div>

      <div className="flex justify-between mt-1">
        <span className="text-xs text-muted-foreground">{formatLabel(min)}</span>
        <span className="text-xs text-muted-foreground">{formatLabel(max)}</span>
      </div>
    </div>
  )
}
