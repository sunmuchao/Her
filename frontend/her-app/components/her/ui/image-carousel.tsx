'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Image from 'next/image'
import { shouldBypassNextImageOptimization } from '@/lib/image-url'
import { cn } from '@/lib/utils'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface ImageCarouselProps {
  images: string[]
  alt?: string
  className?: string
  aspectRatio?: 'square' | 'portrait' | 'landscape'
  showArrows?: boolean
  showIndicators?: boolean
  indicatorStyle?: 'dots' | 'pills' | 'numbers'
  autoPlay?: boolean
  autoPlayIntervalMs?: number
  pauseOnHover?: boolean
  onUserNavigate?: (nextIndex: number) => void
}

export function ImageCarousel({
  images,
  alt = 'Image',
  className,
  aspectRatio = 'portrait',
  showArrows = false,
  showIndicators = true,
  indicatorStyle = 'pills',
  autoPlay = true,
  autoPlayIntervalMs = 3000,
  pauseOnHover = true,
  onUserNavigate,
}: ImageCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const touchStartX = useRef(0)
  const touchEndX = useRef(0)
  const [isPaused, setIsPaused] = useState(false)

  const aspectClasses = {
    square: 'aspect-square',
    portrait: 'aspect-[3/4]',
    landscape: 'aspect-[4/3]'
  }

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    touchEndX.current = e.touches[0].clientX
  }

  const handleTouchEnd = () => {
    const diff = touchStartX.current - touchEndX.current
    const threshold = 50

    if (diff > threshold && currentIndex < images.length - 1) {
      setCurrentIndex(prev => {
        const next = prev + 1
        onUserNavigate?.(next)
        return next
      })
    } else if (diff < -threshold && currentIndex > 0) {
      setCurrentIndex(prev => {
        const next = prev - 1
        onUserNavigate?.(next)
        return next
      })
    }
  }

  const goTo = useCallback((index: number) => {
    const next = Math.max(0, Math.min(index, images.length - 1))
    onUserNavigate?.(next)
    setCurrentIndex(next)
  }, [images.length, onUserNavigate])

  const goNext = useCallback(() => {
    if (currentIndex < images.length - 1) {
      setCurrentIndex(prev => {
        const next = prev + 1
        onUserNavigate?.(next)
        return next
      })
    }
  }, [currentIndex, images.length, onUserNavigate])

  const goPrev = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => {
        const next = prev - 1
        onUserNavigate?.(next)
        return next
      })
    }
  }, [currentIndex, onUserNavigate])

  useEffect(() => {
    setCurrentIndex((prev) => Math.min(prev, Math.max(0, images.length - 1)))
  }, [images.length])

  useEffect(() => {
    if (!autoPlay || images.length <= 1 || isPaused) return
    const timer = window.setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % images.length)
    }, autoPlayIntervalMs)
    return () => window.clearInterval(timer)
  }, [autoPlay, autoPlayIntervalMs, images.length, isPaused])

  if (images.length === 0) return null

  return (
    <div
      className={cn('relative w-full overflow-hidden', aspectClasses[aspectRatio], className)}
      onMouseEnter={() => pauseOnHover && setIsPaused(true)}
      onMouseLeave={() => pauseOnHover && setIsPaused(false)}
      onTouchStart={() => setIsPaused(true)}
      onTouchEnd={() => setIsPaused(false)}
      onFocusCapture={() => setIsPaused(true)}
      onBlurCapture={() => setIsPaused(false)}
    >
      {/* Images container */}
      <div
        ref={containerRef}
        className="flex h-full transition-transform duration-300 ease-out"
        style={{ transform: `translateX(-${currentIndex * 100}%)` }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {images.map((src, index) => (
          <div key={index} className="w-full h-full flex-shrink-0 relative">
            <Image
              src={src}
              alt={`${alt} ${index + 1}`}
              fill
              className="object-cover"
              sizes="(max-width: 768px) 100vw, 50vw"
              priority={index === 0}
              loading={index === 0 ? 'eager' : 'lazy'}
              unoptimized={shouldBypassNextImageOptimization(src)}
            />
          </div>
        ))}
      </div>

      {/* Arrow navigation */}
      {showArrows && images.length > 1 && (
        <>
          <button
            onClick={goPrev}
            className={cn(
              'absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white transition-opacity',
              currentIndex === 0 && 'opacity-30 cursor-not-allowed'
            )}
            disabled={currentIndex === 0}
            aria-label="Previous image"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <button
            onClick={goNext}
            className={cn(
              'absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white transition-opacity',
              currentIndex === images.length - 1 && 'opacity-30 cursor-not-allowed'
            )}
            disabled={currentIndex === images.length - 1}
            aria-label="Next image"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </>
      )}

      {/* Indicators */}
      {showIndicators && images.length > 1 && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5">
          {indicatorStyle === 'dots' && images.map((_, index) => (
            <button
              key={index}
              onClick={() => goTo(index)}
              className={cn(
                'w-2 h-2 rounded-full transition-all',
                index === currentIndex
                  ? 'bg-white scale-110'
                  : 'bg-white/50 hover:bg-white/75'
              )}
              aria-label={`Go to image ${index + 1}`}
              aria-current={index === currentIndex}
            />
          ))}

          {indicatorStyle === 'pills' && (
            <div className="flex gap-1 bg-black/30 backdrop-blur-sm rounded-full px-2 py-1">
              {images.map((_, index) => (
                <button
                  key={index}
                  onClick={() => goTo(index)}
                  className={cn(
                    'h-1 rounded-full transition-all',
                    index === currentIndex
                      ? 'w-4 bg-white'
                      : 'w-1 bg-white/50 hover:bg-white/75'
                  )}
                  aria-label={`Go to image ${index + 1}`}
                  aria-current={index === currentIndex}
                />
              ))}
            </div>
          )}

          {indicatorStyle === 'numbers' && (
            <div className="bg-black/30 backdrop-blur-sm rounded-full px-3 py-1">
              <span className="text-white text-xs font-medium">
                {currentIndex + 1} / {images.length}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
