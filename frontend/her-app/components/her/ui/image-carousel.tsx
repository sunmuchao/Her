'use client'

import { useState, useRef, useCallback } from 'react'
import Image from 'next/image'
import { isLocalDevCdnUrl } from '@/lib/image-url'
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
}

export function ImageCarousel({
  images,
  alt = 'Image',
  className,
  aspectRatio = 'portrait',
  showArrows = false,
  showIndicators = true,
  indicatorStyle = 'pills'
}: ImageCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const touchStartX = useRef(0)
  const touchEndX = useRef(0)

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
      setCurrentIndex(prev => prev + 1)
    } else if (diff < -threshold && currentIndex > 0) {
      setCurrentIndex(prev => prev - 1)
    }
  }

  const goTo = useCallback((index: number) => {
    setCurrentIndex(Math.max(0, Math.min(index, images.length - 1)))
  }, [images.length])

  const goNext = useCallback(() => {
    if (currentIndex < images.length - 1) {
      setCurrentIndex(prev => prev + 1)
    }
  }, [currentIndex, images.length])

  const goPrev = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex(prev => prev - 1)
    }
  }, [currentIndex])

  if (images.length === 0) return null

  return (
    <div className={cn('relative w-full overflow-hidden', aspectClasses[aspectRatio], className)}>
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
              unoptimized={isLocalDevCdnUrl(src)}
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
