'use client'

import { LogOut } from 'lucide-react'
import { clearSession } from '@/lib/auth/session'
import { PageTransition } from './ui/animations'
import { PageHeader } from './ui/page-header'
import { notifySuccess } from '@/lib/notify'

interface SettingsPageProps {
  onBack: () => void
}

/**
 * 设置页面
 *
 * 设计原则：
 * - 只展示已实现的功能
 * - 未实现的功能隐藏而非禁用，避免用户困惑
 * - 信任中心入口已移至 ProfilePage，避免导航循环
 */
export default function SettingsPage({
  onBack,
}: SettingsPageProps) {
  const handleLogout = () => {
    clearSession()
    notifySuccess('已退出登录')
    window.location.href = '/welcome'
  }

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {/* Header - 使用统一组件 */}
      <PageHeader title="设置" showBack onBack={onBack} />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {/* 退出登录按钮 */}
        <section className="mt-6">
          <button
            type="button"
            onClick={handleLogout}
            className="w-full bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-center gap-2 hover:bg-secondary/50 transition-colors focus-ring"
            aria-label="退出登录"
          >
            <LogOut className="w-5 h-5 text-rose" aria-hidden="true" />
            <span className="text-sm text-rose font-medium">退出登录</span>
          </button>
        </section>

        {/* 版本信息 */}
        <div className="text-center text-xs text-muted-foreground pt-4">
          Her v1.0.0
        </div>
      </div>
    </PageTransition>
  )
}
