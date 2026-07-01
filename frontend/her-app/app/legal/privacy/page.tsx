'use client'

import { useRouter } from 'next/navigation'
import { PageHeader } from '@/components/her/ui/page-header'

export default function PrivacyPage() {
  const router = useRouter()

  return (
    <div className="min-h-dvh bg-background">
      <PageHeader
        title="隐私政策"
        subtitle="说明资料、聊天和认证信息如何被使用"
        showBack
        onBack={() => router.back()}
      />

      <main className="mx-auto max-w-md space-y-4 px-4 py-4 pb-10">
        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">1. 我们收集哪些信息</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            为了完成登录、资料展示、推荐匹配和账号安全，我们会处理你主动提交的手机号、昵称、头像、个人资料、
            认证材料、聊天内容以及使用过程中的基础操作记录。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">2. 这些信息会用于什么</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            这些信息主要用于建立账号、生成个人页面、完成匹配推荐、展示关系进度、进行认证审核，以及处理投诉、申诉和安全风控。
            我们不会把你的资料用于与你当前使用目的无关的公开展示。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">3. 谁可以看到你的信息</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            不同信息有不同展示范围。公开资料会用于候选页展示，认证材料和风控信息仅用于审核与安全处理。
            后续如果开放更细的隐私设置，展示范围会以页面开关和说明为准。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">4. 账号安全与找回</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            为了减少账号丢失风险，建议尽量绑定手机号。更换微信或设备后，可以通过“账号找回”重新验证身份。
            你也应妥善保管自己的登录设备，避免将验证码透露给他人。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">5. 问题反馈</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            如果你对资料处理、聊天显示、认证审核或信息使用方式有疑问，可以在设置页通过“意见反馈”提交说明，
            便于我们排查问题并改进处理方式。
          </p>
        </section>
      </main>
    </div>
  )
}
