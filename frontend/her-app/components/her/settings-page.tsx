'use client'

import { useMemo } from 'react'
import { useRouter } from 'next/navigation'
import {
  CircleHelp,
  FileText,
  KeyRound,
  LogOut,
  MessageSquareHeart,
  ShieldCheck,
  Smartphone,
} from 'lucide-react'
import { clearSession } from '@/lib/auth/session'
import { useAuthMe } from '@/lib/hooks/use-auth-me'
import { notifySuccess } from '@/lib/notify'
import { cn } from '@/lib/utils'
import { PageTransition } from './ui/animations'
import { PageHeader } from './ui/page-header'

interface SettingsPageProps {
  onBack: () => void
}

type SettingsItem = {
  key: string
  label: string
  value?: string
  description?: string
  icon: React.ElementType
  interactive?: boolean
}

function maskPhone(phone?: string): string {
  if (!phone) return '未绑定手机号'
  if (phone.length < 7) return phone
  return `${phone.slice(0, 3)}****${phone.slice(-4)}`
}

function getAuthSourceLabel(source?: string): string {
  if (source === 'wechat') return '微信登录'
  if (source === 'sms') return '手机号登录'
  return '当前登录'
}

/**
 * 设置页面
 *
 * 当前优先补齐“账号安全”和“帮助”信息，
 * 先让用户看得到账号状态、找得到帮助入口，再逐步补完整交互。
 */
export default function SettingsPage({
  onBack,
}: SettingsPageProps) {
  const router = useRouter()
  const { data: auth } = useAuthMe()

  const accountItems = useMemo<SettingsItem[]>(() => {
    const phone = auth?.user?.phone
    const authSource = auth?.principal?.auth_source

    return [
      {
        key: 'phone',
        label: '绑定手机号',
        value: maskPhone(phone),
        description: phone ? '已用于登录和找回账号' : '建议尽快绑定，避免账号丢失',
        icon: Smartphone,
      },
      {
        key: 'login-method',
        label: '当前登录方式',
        value: getAuthSourceLabel(authSource),
        description: '后续可继续补充更多登录方式管理',
        icon: ShieldCheck,
      },
      {
        key: 'recovery',
        label: '账号找回',
        value: '手机号验证',
        description: phone ? '通过已绑定手机号完成验证找回' : '未绑定手机号时，找回能力会受限',
        icon: KeyRound,
        interactive: true,
      },
    ]
  }, [auth])

  const helpItems = useMemo<SettingsItem[]>(
    () => [
      {
        key: 'feedback',
        label: '意见反馈',
        value: '告诉我们你遇到的问题',
        description: '适合反馈 bug、体验问题和建议',
        icon: MessageSquareHeart,
        interactive: true,
      },
      {
        key: 'agreement',
        label: '用户协议',
        description: '查看产品使用规则和账号责任说明',
        icon: FileText,
        interactive: true,
      },
      {
        key: 'privacy',
        label: '隐私政策',
        description: '查看资料、聊天与认证信息如何被使用',
        icon: FileText,
        interactive: true,
      },
    ],
    [],
  )

  const handleItemClick = (key: string) => {
    switch (key) {
      case 'recovery':
        router.push('/recovery')
        break
      case 'feedback':
        router.push('/help/feedback')
        break
      case 'agreement':
        router.push('/legal/terms')
        break
      case 'privacy':
        router.push('/legal/privacy')
        break
      default:
        break
    }
  }

  const handleLogout = () => {
    clearSession()
    notifySuccess('已退出登录')
    window.location.href = '/welcome'
  }

  return (
    <PageTransition className="flex flex-col h-full bg-background">
      <PageHeader title="设置" showBack onBack={onBack} />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 pb-20">
        <section className="space-y-2">
          <h2 className="px-1 text-xs text-muted-foreground">账号安全</h2>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {accountItems.map((item, index) => {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => {
                    if (!item.interactive) return
                    handleItemClick(item.key)
                  }}
                  className={cn(
                    'flex w-full items-start gap-3 px-4 py-3 text-left',
                    index !== accountItems.length - 1 && 'border-b border-border',
                    item.interactive ? 'transition-colors hover:bg-secondary/50 focus-ring' : 'cursor-default',
                  )}
                >
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm">{item.label}</span>
                      {item.value ? (
                        <span className="shrink-0 text-xs text-muted-foreground">{item.value}</span>
                      ) : null}
                    </div>
                    {item.description ? (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.description}</p>
                    ) : null}
                  </div>
                </button>
              )
            })}
          </div>

          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <p className="text-sm font-medium">安全说明</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              绑定手机号后，账号更容易找回，也更适合在更换微信或设备后继续登录使用。
            </p>
          </div>
        </section>

        <section className="space-y-2">
          <h2 className="px-1 text-xs text-muted-foreground">帮助</h2>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {helpItems.map((item, index) => {
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => handleItemClick(item.key)}
                  className={cn(
                    'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-secondary/50 focus-ring',
                    index !== helpItems.length - 1 && 'border-b border-border',
                  )}
                >
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">{item.label}</div>
                    {item.value ? (
                      <div className="mt-0.5 text-xs text-muted-foreground">{item.value}</div>
                    ) : null}
                    {item.description ? (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.description}</p>
                    ) : null}
                  </div>
                </button>
              )
            })}
          </div>

          <div className="rounded-xl border border-border bg-card px-4 py-3">
            <div className="flex items-center gap-2">
              <CircleHelp className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <p className="text-sm font-medium">常见问题</p>
            </div>
            <div className="mt-2 space-y-1 text-xs leading-5 text-muted-foreground">
              <p>收不到验证码时，先确认手机号填写正确，再检查网络和短信拦截设置。</p>
              <p>认证材料提交后，可在“我的认证”里继续查看进度，审核完成前会显示“审核中”。</p>
              <p>如果消息没有及时刷新，可以先返回列表页重试，后续会补充更完整的通知设置。</p>
            </div>
          </div>
        </section>

        <section className="mt-6">
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-3 transition-colors hover:bg-secondary/50 focus-ring"
            aria-label="退出登录"
          >
            <LogOut className="h-5 w-5 text-rose" aria-hidden="true" />
            <span className="text-sm font-medium text-rose">退出登录</span>
          </button>
        </section>

        <div className="pt-4 text-center text-xs text-muted-foreground">Her v1.0.0</div>
      </div>
    </PageTransition>
  )
}
