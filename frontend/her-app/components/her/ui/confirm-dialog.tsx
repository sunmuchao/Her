'use client'

import { createPortal } from 'react-dom'
import { AlertCircle } from 'lucide-react'

/**
 * 确认对话框 Props
 */
export interface ConfirmDialogProps {
  /** 是否显示 */
  open: boolean
  /** 标题 */
  title: string
  /** 描述文字 */
  description: string
  /** 确认按钮文字 */
  confirmLabel?: string
  /** 取消按钮文字 */
  cancelLabel?: string
  /** 语气（默认/危险） */
  tone?: 'default' | 'destructive'
  /** 确认回调 */
  onConfirm: () => void
  /** 取消回调 */
  onCancel: () => void
}

/**
 * 确认对话框组件
 *
 * 统一的确认/删除对话框，支持：
 * - Portal 渲染（避免被父容器影响）
 * - 动画效果（淡入 + 缩放）
 * - 危险操作样式（红色按钮）
 *
 * 使用场景：
 * - RelationshipsPage 删除关系确认
 * - 其他需要二次确认的操作
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  cancelLabel = '取消',
  tone = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-fade-in"
      onClick={(e) => {
        // 点击遮罩不关闭（强制用户明确选择）
        e.stopPropagation()
      }}
    >
      <div className="mx-4 w-full max-w-sm rounded-2xl bg-card p-5 shadow-xl animate-scale-in">
        {/* Header：图标 + 标题 */}
        <div className="flex items-center gap-3 mb-3">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center ${
              tone === 'destructive' ? 'bg-destructive/10' : 'bg-primary/10'
            }`}
          >
            <AlertCircle
              className={`w-5 h-5 ${
                tone === 'destructive' ? 'text-destructive' : 'text-primary'
              }`}
            />
          </div>
          <h3 className="text-base font-medium">{title}</h3>
        </div>

        {/* 描述文字 */}
        <p className="text-sm text-muted-foreground mb-5">{description}</p>

        {/* 按钮：取消 + 确认 */}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-medium hover:bg-secondary/50 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`flex-1 rounded-lg px-4 py-2.5 text-sm font-medium text-white transition-colors ${
              tone === 'destructive'
                ? 'bg-destructive hover:bg-destructive/90'
                : 'bg-primary hover:bg-primary/90'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}