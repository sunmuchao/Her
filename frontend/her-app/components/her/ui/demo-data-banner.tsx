'use client'

import { Info } from 'lucide-react'

export function DemoDataBanner() {
  return (
    <div
      className="mx-4 mt-2 mb-1 flex items-start gap-2 rounded-lg border border-amber-200/80 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-100"
      role="status"
    >
      <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      <span>当前展示的是演示数据（接口不可用或开发 Mock 已开启）</span>
    </div>
  )
}
