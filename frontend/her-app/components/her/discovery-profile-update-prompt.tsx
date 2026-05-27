'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  confirmDiscoveryProfileUpdate,
  rejectDiscoveryProfileUpdate,
} from '@/lib/api/endpoints/discovery'
import { notifyError, notifySuccess } from '@/lib/notify'
import type { DiscoveryProfileUpdatePromptItem } from '@/lib/discovery/map-discovery-view'

interface DiscoveryProfileUpdatePromptProps {
  sessionId: string
  item: DiscoveryProfileUpdatePromptItem
  onResolved?: (status: 'confirmed' | 'rejected') => void
}

export function DiscoveryProfileUpdatePrompt({
  sessionId,
  item,
  onResolved,
}: DiscoveryProfileUpdatePromptProps) {
  const [status, setStatus] = useState(item.status)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const isPending = status === 'pending'

  const handleConfirm = async () => {
    if (!isPending || isSubmitting) return
    setIsSubmitting(true)
    try {
      await confirmDiscoveryProfileUpdate(sessionId, item.requestId)
      setStatus('confirmed')
      notifySuccess('资料已更新')
      onResolved?.('confirmed')
    } catch (error) {
      notifyError(error, '资料更新失败')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!isPending || isSubmitting) return
    setIsSubmitting(true)
    try {
      await rejectDiscoveryProfileUpdate(sessionId, item.requestId)
      setStatus('rejected')
      onResolved?.('rejected')
    } catch (error) {
      notifyError(error, '操作失败')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="max-w-[92%] rounded-2xl border border-border bg-card p-4 shadow-sm">
      <p className="text-sm font-medium text-foreground">{item.title}</p>
      <ul className="mt-3 space-y-2 text-sm">
        {item.changes.map(change => (
          <li key={change.field} className="flex flex-wrap items-center gap-1">
            <span className="text-muted-foreground">{change.label}</span>
            <span className="text-muted-foreground">{formatValue(change.from)}</span>
            <span className="text-muted-foreground">→</span>
            <span className="font-medium text-foreground">{formatValue(change.to)}</span>
          </li>
        ))}
      </ul>
      {isPending ? (
        <div className="mt-4 flex gap-2">
          <Button size="sm" onClick={handleConfirm} disabled={isSubmitting}>
            确认更新
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleReject}
            disabled={isSubmitting}
          >
            暂不更新
          </Button>
        </div>
      ) : (
        <p
          className={cn(
            'mt-3 text-xs',
            status === 'confirmed' ? 'text-emerald-600' : 'text-muted-foreground',
          )}
        >
          {status === 'confirmed' ? '已更新' : '已忽略'}
        </p>
      )}
      {item.timestamp ? (
        <p className="mt-2 text-[10px] text-muted-foreground">{item.timestamp}</p>
      ) : null}
    </div>
  )
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}
