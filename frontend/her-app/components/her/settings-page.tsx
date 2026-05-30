'use client'

import { ChevronRight, User, Moon, LogOut } from 'lucide-react'
import { clearSession } from '@/lib/auth/session'
import { cn } from '@/lib/utils'
import { PageTransition } from './ui/animations'
import { PageHeader } from './ui/page-header'
import { notifySuccess } from '@/lib/notify'

interface SettingsPageProps {
  onBack: () => void
  onThemeToggle?: () => void
  onOpenOnboarding?: () => void
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
  onThemeToggle,
  onOpenOnboarding,
}: SettingsPageProps) {
  const handleItemClick = (key: string) => {
    switch (key) {
      case 'profile':
        onOpenOnboarding?.()
        break
      case 'theme':
        onThemeToggle?.()
        break
    }
  }

  const handleLogout = () => {
    clearSession()
    notifySuccess('已退出登录')
    window.location.href = '/welcome'
  }

  // 设置项定义 - 只展示已实现的功能
  // 注意：信任中心入口已移至 ProfilePage，避免导航循环
  const settingsSections = [
    {
      title: '账号',
      items: [
        { icon: User, label: '编辑资料', key: 'profile' },
      ],
    },
    {
      title: '显示与交互',
      items: [
        { icon: Moon, label: '深色模式', key: 'theme' },
        // 通知设置暂时隐藏，功能未实现
        // { icon: Bell, label: '通知设置', key: 'notifications' },
      ],
    },
    // 关于部分暂时隐藏，功能未实现
    // {
    //   title: '关于',
    //   items: [
    //     { icon: Info, label: '关于我们', key: 'about' },
    //     { icon: Trash2, label: '清除缓存', key: 'cache' },
    //   ],
    // },
  ]

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      {/* Header - 使用统一组件 */}
      <PageHeader title="设置" showBack onBack={onBack} />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        {settingsSections.map((section) => (
          <section key={section.title}>
            <h2 className="text-xs text-muted-foreground mb-2 px-1">{section.title}</h2>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {section.items.map((item, i, arr) => {
                const Icon = item.icon
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => handleItemClick(item.key)}
                    className={cn(
                      'w-full px-4 py-3 flex items-center gap-3 text-left transition-colors focus-ring',
                      i !== arr.length - 1 && 'border-b border-border',
                      'hover:bg-secondary/50',
                    )}
                    aria-label={item.label}
                  >
                    <Icon className="w-5 h-5 text-muted-foreground" aria-hidden="true" />
                    <span className="flex-1 text-sm">{item.label}</span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" aria-hidden="true" />
                  </button>
                )
              })}
            </div>
          </section>
        ))}

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