'use client'

import { useState, useRef, KeyboardEvent, ChangeEvent } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface TagsInputProps {
  /** 已添加的标签列表 */
  value: string[]
  /** 标签变化回调 */
  onChange: (tags: string[]) => void
  /** 最大标签数量 */
  maxTags?: number
  /** 单个标签最大长度 */
  maxLength?: number
  /** 占位符文本 */
  placeholder?: string
  /** 自定义样式 */
  className?: string
  /** 是否禁用 */
  disabled?: boolean
}

/**
 * 标签输入组件
 *
 * 功能：
 * - 回车或逗号分隔添加新标签
 * - 点击 × 删除标签
 * - 限制最多 maxTags 个标签
 * - 限制单个标签 maxLength 字符
 */
export function TagsInput({
  value,
  onChange,
  maxTags = 6,
  maxLength = 20,
  placeholder = '输入新标签...',
  className,
  disabled = false,
}: TagsInputProps) {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // 添加标签
  const addTag = (tag: string) => {
    const trimmed = tag.trim()
    if (!trimmed) return

    // 检查长度限制
    if (trimmed.length > maxLength) {
      // 截断到 maxLength
      trimmed.slice(0, maxLength)
    }

    // 检查数量限制
    if (value.length >= maxTags) return

    // 检查重复
    if (value.includes(trimmed)) return

    onChange([...value, trimmed.slice(0, maxLength)])
    setInputValue('')
  }

  // 删除标签
  const removeTag = (index: number) => {
    const newTags = [...value]
    newTags.splice(index, 1)
    onChange(newTags)
  }

  // 处理键盘事件
  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return

    // 回车或逗号添加标签
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTag(inputValue)
    }

    // Backspace 在输入为空时删除最后一个标签
    if (e.key === 'Backspace' && inputValue === '' && value.length > 0) {
      removeTag(value.length - 1)
    }
  }

  // 处理输入变化
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value)
  }

  // 处理粘贴（支持逗号分隔的多个标签）
  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    if (disabled) return
    e.preventDefault()
    const pastedText = e.clipboardData.getData('text')
    const tags = pastedText.split(/[,，]/).map(t => t.trim()).filter(Boolean)

    // 逐个添加，直到达到 maxTags
    const newTags = [...value]
    for (const tag of tags) {
      if (newTags.length >= maxTags) break
      const trimmed = tag.slice(0, maxLength)
      if (trimmed && !newTags.includes(trimmed)) {
        newTags.push(trimmed)
      }
    }
    onChange(newTags)
    setInputValue('')
  }

  // 点击容器聚焦输入框
  const handleContainerClick = () => {
    if (!disabled && inputRef.current) {
      inputRef.current.focus()
    }
  }

  return (
    <div
      className={cn(
        'flex flex-wrap gap-1.5 p-2 rounded-lg border border-border bg-background cursor-text',
        disabled && 'opacity-50 cursor-not-allowed',
        className,
      )}
      onClick={handleContainerClick}
    >
      {/* 已添加标签 */}
      {value.map((tag, index) => (
        <span
          key={`${tag}-${index}`}
          className="inline-flex items-center gap-1 px-2 py-1 bg-secondary text-xs text-muted-foreground rounded-md"
        >
          {tag}
          {!disabled && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                removeTag(index)
              }}
              className="w-3 h-3 flex items-center justify-center hover:text-primary transition-colors"
              aria-label={`删除标签 ${tag}`}
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </span>
      ))}

      {/* 输入框 */}
      {!disabled && value.length < maxTags && (
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={value.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[80px] text-xs bg-transparent outline-none placeholder:text-muted-foreground/50"
          maxLength={maxLength}
        />
      )}

      {/* 达到上限提示 */}
      {value.length >= maxTags && !disabled && (
        <span className="text-xs text-muted-foreground/50">最多 {maxTags} 个标签</span>
      )}
    </div>
  )
}