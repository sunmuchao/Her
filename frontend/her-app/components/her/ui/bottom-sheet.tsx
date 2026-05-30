'use client'

import { createPortal } from 'react-dom'
import { useState, useRef, type ReactNode } from 'react'

/**
 * 底部面板 Props
 */
export interface BottomSheetProps {
  /** 是否显示 */
  open: boolean
  /** 关闭回调 */
  onClose: () => void
  /** 面板内容 */
  children: ReactNode
  /** 最小高度（px） */
  minHeight?: number
  /** 最大高度（px） */
  maxHeight?: number
  /** 默认高度（px） */
  defaultHeight?: number
  /** 关闭阈值（低于此高度自动关闭） */
  closeThreshold?: number
  /** 是否显示拖动手柄 */
  showHandle?: boolean
}

/**
 * 底部面板组件
 *
 * 支持自由拖拽高度，用于：
 * - 小雅复盘面板
 * - 其他需要底部弹出的交互面板
 *
 * 特性：
 * - Portal 渲染（避开父容器 transform 影响）
 * - 手势拖拽（上拖增加高度，下拖减少高度）
 * - 低于阈值自动关闭
 * - 安全区域适配（safe-area-inset-bottom）
 */
export function BottomSheet({
  open,
  onClose,
  children,
  minHeight = 180,
  maxHeight = 500,
  defaultHeight = 350,
  closeThreshold = 120,
  showHandle = true,
}: BottomSheetProps) {
  const [height, setHeight] = useState(defaultHeight)
  const dragStartY = useRef(0)
  const dragStartHeight = useRef(defaultHeight)

  // 打开时重置高度
  // handleClose 会在 onClose 中调用，确保下次打开时恢复默认高度

  if (!open) return null

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    dragStartY.current = e.clientY
    dragStartHeight.current = height
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return
    const delta = dragStartY.current - e.clientY
    // 向上拖动增加高度，向下拖动减少高度
    const newHeight = dragStartHeight.current + delta

    // 限制在最小和最大高度之间
    if (newHeight >= minHeight && newHeight <= maxHeight) {
      setHeight(newHeight)
    } else if (newHeight < minHeight) {
      setHeight(minHeight)
    } else if (newHeight > maxHeight) {
      setHeight(maxHeight)
    }
  }

  function handlePointerUp(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.releasePointerCapture(e.pointerId)
    // 如果高度低于关闭阈值，关闭面板
    if (height < closeThreshold) {
      onClose()
    }
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50"
      onClick={(e) => {
        // 点击遮罩关闭
        if (e.target === e.currentTarget) {
          onClose()
        }
      }}
    >
      {/* 背景遮罩 */}
      <div className="fixed inset-0 bg-black/30 animate-fade-in" />

      {/* 底部面板 */}
      <div
        className="fixed bottom-0 left-0 right-0 z-10 bg-background rounded-t-2xl shadow-xl overflow-hidden flex flex-col"
        style={{
          height: height,
          maxHeight: '90vh',
          paddingBottom: 'env(safe-area-inset-bottom, 16px)',
          animation: 'bottom-sheet-in 300ms cubic-bezier(0.16, 1, 0.3, 1) forwards',
          transition: 'height 0ms', // 拖动时无过渡，响应更快
        }}
      >
        {/* 拖动手柄 */}
        {showHandle && (
          <div
            className="shrink-0 flex justify-center py-3 cursor-grab active:cursor-grabbing touch-none"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
            <div className="w-10 h-1 rounded-full bg-border" />
          </div>
        )}

        {/* 内容区域 */}
        <div className="flex-1 overflow-hidden">{children}</div>
      </div>
    </div>,
    document.body
  )
}