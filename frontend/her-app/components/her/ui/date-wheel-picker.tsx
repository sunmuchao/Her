'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Calendar } from 'lucide-react'
import { cn } from '@/lib/utils'

interface DateWheelPickerProps {
  value: string // YYYY-MM-DD format
  onChange: (date: string) => void
  minYear?: number
  maxYear?: number
  placeholder?: string
}

export function DateWheelPicker({ 
  value, 
  onChange, 
  minYear = 1950,
  maxYear = new Date().getFullYear() - 18,
  placeholder = '选择日期'
}: DateWheelPickerProps) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Parse value or use defaults
  const parsed = value ? new Date(value) : null
  const [year, setYear] = useState(parsed?.getFullYear() || 1995)
  const [month, setMonth] = useState(parsed ? parsed.getMonth() + 1 : 1)
  const [day, setDay] = useState(parsed?.getDate() || 1)

  // Generate arrays
  const years = Array.from({ length: maxYear - minYear + 1 }, (_, i) => maxYear - i)
  const months = Array.from({ length: 12 }, (_, i) => i + 1)
  const daysInMonth = new Date(year, month, 0).getDate()
  const days = Array.from({ length: daysInMonth }, (_, i) => i + 1)

  // Adjust day if it exceeds days in selected month
  useEffect(() => {
    if (day > daysInMonth) {
      setDay(daysInMonth)
    }
  }, [day, daysInMonth])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleConfirm = () => {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    onChange(dateStr)
    setIsOpen(false)
  }

  const formatDisplayDate = () => {
    if (!value) return placeholder
    const d = new Date(value)
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
  }

  // Calculate age
  const calculateAge = () => {
    const today = new Date()
    let age = today.getFullYear() - year
    const monthDiff = today.getMonth() + 1 - month
    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < day)) {
      age--
    }
    return age
  }

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={cn(
          'w-full px-4 py-3.5 rounded-xl text-base text-left transition-all bg-input border-2 border-border',
          'hover:border-primary/30 focus:border-primary focus:ring-1 focus:ring-primary focus-ring',
          value ? 'text-foreground' : 'text-muted-foreground'
        )}
      >
        <span className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-muted-foreground" />
          {formatDisplayDate()}
          {value && (
            <span className="ml-auto text-sm text-muted-foreground">
              {calculateAge()}岁
            </span>
          )}
        </span>
      </button>
    )
  }

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button showing current selection */}
      <button
        type="button"
        onClick={() => setIsOpen(false)}
        className="w-full px-4 py-3.5 rounded-xl text-base text-left transition-all bg-input border-2 border-primary ring-1 ring-primary text-foreground"
      >
        <span className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-primary" />
          {`${year}年${month}月${day}日`}
          <span className="ml-auto text-sm text-muted-foreground">
            {calculateAge()}岁
          </span>
        </span>
      </button>

      {/* Wheel picker dropdown */}
      <div className="absolute z-50 w-full mt-2 bg-card border border-border rounded-xl shadow-lg animate-scale-in overflow-hidden">
        {/* Wheels container */}
        <div className="flex h-48 relative">
          {/* Highlight bar */}
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-10 bg-secondary/50 pointer-events-none border-y border-border" />
          
          {/* Year wheel */}
          <WheelColumn
            items={years}
            value={year}
            onChange={setYear}
            suffix="年"
          />
          
          {/* Month wheel */}
          <WheelColumn
            items={months}
            value={month}
            onChange={setMonth}
            suffix="月"
          />
          
          {/* Day wheel */}
          <WheelColumn
            items={days}
            value={day}
            onChange={setDay}
            suffix="日"
          />
        </div>

        {/* Confirm button */}
        <div className="p-3 border-t border-border">
          <button
            type="button"
            onClick={handleConfirm}
            className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-medium transition-all hover:bg-primary/90 active:scale-[0.98]"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  )
}

interface WheelColumnProps {
  items: number[]
  value: number
  onChange: (value: number) => void
  suffix: string
}

function WheelColumn({ items, value, onChange, suffix }: WheelColumnProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const itemHeight = 40
  const isScrolling = useRef(false)
  const scrollTimeout = useRef<ReturnType<typeof setTimeout>>()

  // Scroll to selected value on mount
  useEffect(() => {
    const container = containerRef.current
    if (container) {
      const index = items.indexOf(value)
      if (index !== -1) {
        container.scrollTop = index * itemHeight
      }
    }
  }, [])

  const handleScroll = useCallback(() => {
    if (scrollTimeout.current) {
      clearTimeout(scrollTimeout.current)
    }

    isScrolling.current = true

    scrollTimeout.current = setTimeout(() => {
      const container = containerRef.current
      if (container) {
        const scrollTop = container.scrollTop
        const index = Math.round(scrollTop / itemHeight)
        const clampedIndex = Math.max(0, Math.min(items.length - 1, index))
        
        // Snap to nearest item
        container.scrollTo({
          top: clampedIndex * itemHeight,
          behavior: 'smooth'
        })
        
        // Update value
        if (items[clampedIndex] !== value) {
          onChange(items[clampedIndex])
        }
      }
      isScrolling.current = false
    }, 100)
  }, [items, value, onChange])

  return (
    <div 
      ref={containerRef}
      className="flex-1 h-full overflow-y-auto scrollbar-hide snap-y snap-mandatory"
      onScroll={handleScroll}
      style={{ 
        scrollSnapType: 'y mandatory',
        paddingTop: `${itemHeight * 2}px`,
        paddingBottom: `${itemHeight * 2}px`
      }}
    >
      {items.map((item) => (
        <div
          key={item}
          className={cn(
            'h-10 flex items-center justify-center text-base transition-all snap-center',
            item === value 
              ? 'text-foreground font-medium scale-105' 
              : 'text-muted-foreground scale-95 opacity-60'
          )}
          style={{ scrollSnapAlign: 'center' }}
          onClick={() => {
            onChange(item)
            const container = containerRef.current
            if (container) {
              const index = items.indexOf(item)
              container.scrollTo({
                top: index * itemHeight,
                behavior: 'smooth'
              })
            }
          }}
        >
          {item}{suffix}
        </div>
      ))}
    </div>
  )
}
