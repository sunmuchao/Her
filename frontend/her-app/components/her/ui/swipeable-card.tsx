'use client'

import { useEffect, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'

/**
 * 滑动操作配置
 */
export interface SwipeAction {
  key: string
  label: string
  icon: LucideIcon
  tone?: 'default' | 'destructive'
  onClick: () => void
}

/**
 * 滑动卡片组件 Props
 */
export interface SwipeableCardProps {
  /** 是否展开操作菜单 */
  open: boolean
  /** 展开/收起回调 */
  onOpenChange: (next: boolean) => void
  /** 操作按钮列表 */
  actions: SwipeAction[]
  /** 点击卡片主体回调 */
  onMainClick?: () => void
  /** 无障碍标签 */
  ariaLabel?: string
  /** 自定义样式 */
  className?: string
  /** 自定义内联样式 */
  style?: React.CSSProperties
  /** 卡片内容 */
  children: React.ReactNode
  /** 是否已置顶 */
  isPinned?: boolean
  /** 是否有未读 */
  hasUnread?: boolean
}

/**
 * 滑动卡片组件
 *
 * 支持左滑显示操作按钮（置顶、标记已读、删除等）
 * 手势识别：横向滑动才触发，纵向滑动忽略
 *
 * 使用场景：
 * - RelationshipsPage 的关系卡片
 * - 其他需要滑动操作的列表项
 */
export function SwipeableCard({
  open,
  onOpenChange,
  actions,
  onMainClick,
  ariaLabel,
  className,
  style,
  children,
  isPinned,
  hasUnread,
}: SwipeableCardProps) {
  const actionsWidth = actions.length * 76
  const [dragOffset, setDragOffset] = useState(0)
  const gesture = useRef({
    startX: 0,
    startY: 0,
    dragging: false,
    horizontal: false,
    pointerId: -1,
  })

  // 收起时清空偏移
  useEffect(() => {
    if (!open) setDragOffset(0)
  }, [open])

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement | null
    // 点击按钮时不触发手势
    if (target?.closest('button')) return
    gesture.current = {
      startX: event.clientX,
      startY: event.clientY,
      dragging: true,
      horizontal: false,
      pointerId: event.pointerId,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!gesture.current.dragging || gesture.current.pointerId !== event.pointerId) return
    const deltaX = event.clientX - gesture.current.startX
    const deltaY = event.clientY - gesture.current.startY

    // 判断是否为横向滑动
    if (!gesture.current.horizontal) {
      if (Math.abs(deltaX) < 8) return
      if (Math.abs(deltaY) > Math.abs(deltaX)) return
      gesture.current.horizontal = true
    }

    // 计算偏移量
    const nextOffset = open
      ? Math.max(0, Math.min(actionsWidth, actionsWidth - deltaX))
      : Math.max(0, Math.min(actionsWidth, -deltaX))
    setDragOffset(nextOffset)
  }

  function finishGesture(event: React.PointerEvent<HTMLDivElement>) {
    if (gesture.current.pointerId !== event.pointerId) return
    const shouldOpen = dragOffset > actionsWidth * 0.4
    const wasHorizontal = gesture.current.horizontal

    // 重置手势状态
    gesture.current = {
      startX: 0,
      startY: 0,
      dragging: false,
      horizontal: false,
      pointerId: -1,
    }

    setDragOffset(shouldOpen ? actionsWidth : 0)
    onOpenChange(shouldOpen)

    // 非横向滑动且未展开时，触发主体点击
    if (!wasHorizontal && !open && onMainClick) onMainClick()
  }

  const offset = open ? Math.max(actionsWidth, dragOffset) : dragOffset

  return (
    <div className={className} style={style} aria-label={ariaLabel}>
      <div
        className={`relative w-full overflow-hidden rounded-xl ${
          isPinned ? 'ring-2 ring-gold/40' : ''
        } ${hasUnread ? 'ring-2 ring-rose/40' : ''}`}
      >
        {/* 未读指示条 */}
        {hasUnread && (
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-rose z-20 rounded-l-xl" />
        )}

        {/* 右侧操作按钮区 */}
        <div
          className="absolute inset-y-0 right-0 flex justify-end"
          style={{ width: actionsWidth }}
        >
          {actions.map((action) => {
            const Icon = action.icon
            return (
              <button
                key={action.key}
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  action.onClick()
                  onOpenChange(false)
                  setDragOffset(0)
                }}
                className={`flex flex-1 flex-col items-center justify-center gap-1 text-xs text-white ${
                  action.tone === 'destructive' ? 'bg-destructive' : 'bg-primary'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{action.label}</span>
              </button>
            )
          })}
        </div>

        {/* 卡片主体 */}
        <div
          className="relative z-10 w-full bg-card transition-transform duration-200 ease-out touch-pan-y"
          style={{ transform: `translateX(${-offset}px)` }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={finishGesture}
          onPointerCancel={finishGesture}
        >
          {children}
        </div>
      </div>
    </div>
  )
}