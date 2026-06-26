'use client'

import { useState, useRef, useEffect } from 'react'
import { Trash2 } from 'lucide-react'

interface SwipeToDeleteProps {
  children: React.ReactNode
  onDelete: () => void
  deleteLabel?: string
  threshold?: number // 滑动阈值（像素）
}

export function SwipeToDelete({
  children,
  onDelete,
  deleteLabel = '删除',
  threshold = 80,
}: SwipeToDeleteProps) {
  const [translateX, setTranslateX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const startXRef = useRef(0)
  const currentXRef = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const isDraggingRef = useRef(false)
  const shouldPreventClickRef = useRef(false) // 是否应该阻止点击事件

  // 触摸事件处理
  const handleTouchStart = (e: React.TouchEvent) => {
    startXRef.current = e.touches[0].clientX
    currentXRef.current = e.touches[0].clientX
    setIsDragging(true)
    isDraggingRef.current = true
    shouldPreventClickRef.current = false // 开始时允许点击
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isDraggingRef.current) return

    currentXRef.current = e.touches[0].clientX
    const diff = startXRef.current - currentXRef.current

    // 只允许左滑（diff > 0）
    if (diff > 0) {
      setTranslateX(Math.min(diff, threshold + 20))
      setShowDelete(diff > threshold / 2)

      // 如果滑动超过10px，就认为是滑动操作，阻止点击
      if (diff > 10) {
        shouldPreventClickRef.current = true
      }
    } else {
      setTranslateX(0)
      setShowDelete(false)
    }
  }

  const handleTouchEnd = (e: React.TouchEvent) => {
    setIsDragging(false)
    isDraggingRef.current = false

    const diff = startXRef.current - currentXRef.current

    // 如果滑动超过阈值，保持打开状态
    if (diff > threshold) {
      setTranslateX(threshold)
      setShowDelete(true)
    } else {
      // 否则关闭
      setTranslateX(0)
      setShowDelete(false)
    }

    // 如果滑动距离超过10px，阻止点击事件
    if (diff > 10) {
      shouldPreventClickRef.current = true
    }
  }

  // 鼠标事件处理（桌面端）
  const handleMouseDown = (e: React.MouseEvent) => {
    startXRef.current = e.clientX
    currentXRef.current = e.clientX
    setIsDragging(true)
    isDraggingRef.current = true
    shouldPreventClickRef.current = false // 开始时允许点击
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current) return

    currentXRef.current = e.clientX
    const diff = startXRef.current - currentXRef.current

    // 只允许左滑（diff > 0）
    if (diff > 0) {
      setTranslateX(Math.min(diff, threshold + 20))
      setShowDelete(diff > threshold / 2)

      // 如果滑动超过10px，就认为是滑动操作，阻止点击
      if (diff > 10) {
        shouldPreventClickRef.current = true
      }
    } else {
      setTranslateX(0)
      setShowDelete(false)
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
    isDraggingRef.current = false

    const diff = startXRef.current - currentXRef.current

    // 如果滑动超过阈值，保持打开状态
    if (diff > threshold) {
      setTranslateX(threshold)
      setShowDelete(true)
    } else {
      // 否则关闭
      setTranslateX(0)
      setShowDelete(false)
    }

    // 如果滑动距离超过10px，阻止点击事件
    if (diff > 10) {
      shouldPreventClickRef.current = true
    }
  }

  const handleMouseLeave = () => {
    if (isDraggingRef.current) {
      handleMouseUp()
    }
  }

  // 点击事件拦截
  const handleClickCapture = (e: React.MouseEvent | React.TouchEvent) => {
    // 如果应该阻止点击（因为发生了滑动），阻止事件传播
    if (shouldPreventClickRef.current) {
      e.stopPropagation()
      e.preventDefault()
      shouldPreventClickRef.current = false // 重置状态
    }
  }

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation() // 阻止事件传播到卡片
    onDelete()
    setTranslateX(0)
    setShowDelete(false)
  }

  // 点击其他地方时关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setTranslateX(0)
        setShowDelete(false)
      }
    }

    if (showDelete) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [showDelete])

  return (
    <div ref={containerRef} className="relative overflow-hidden select-none">
      {/* 删除按钮（右侧） */}
      <div
        className="absolute right-0 top-0 bottom-0 flex items-center justify-center bg-destructive transition-all"
        style={{
          width: `${translateX}px`,
        }}
      >
        {showDelete && (
          <button
            onClick={handleDeleteClick}
            className="flex items-center gap-1 px-4 text-destructive-foreground hover:bg-destructive/90 transition-colors"
            aria-label={deleteLabel}
          >
            <Trash2 className="w-4 h-4" />
            <span className="text-sm font-medium">{deleteLabel}</span>
          </button>
        )}
      </div>

      {/* 内容（可滑动） */}
      <div
        className="transition-transform duration-200 ease-out"
        style={{
          transform: `translateX(-${translateX}px)`,
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onClickCapture={handleClickCapture} // 拦截点击事件
      >
        {children}
      </div>
    </div>
  )
}