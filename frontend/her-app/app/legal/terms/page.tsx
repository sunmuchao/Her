'use client'

import { useRouter } from 'next/navigation'
import { PageHeader } from '@/components/her/ui/page-header'

export default function TermsPage() {
  const router = useRouter()

  return (
    <div className="min-h-dvh bg-background">
      <PageHeader
        title="用户协议"
        subtitle="说明账号使用、内容发布与服务边界"
        showBack
        onBack={() => router.back()}
      />

      <main className="mx-auto max-w-md space-y-4 px-4 py-4 pb-10">
        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">1. 服务定位</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            Her 旨在帮助用户建立认真关系，提供资料展示、匹配推荐、关系沟通、认证与偏好管理等功能。
            你在使用过程中，应保证提交资料真实、合法，不得冒用他人身份或发布误导性信息。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">2. 账号责任</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            账号由你本人负责保管。请妥善保存登录方式，并尽量绑定手机号，避免因更换设备、微信或手机号造成无法找回。
            如果发现账号异常登录，应尽快退出并通过账号找回重新验证身份。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">3. 内容与行为规范</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            你发布的资料、照片、聊天内容和认证材料，不得包含违法内容、骚扰信息、虚假证明或侵犯他人权益的信息。
            平台可基于审核、风控和投诉处理需要，对相关内容进行核验、限制展示或下架处理。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">4. 功能变更与中断</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            为了修复问题、优化体验或满足合规要求，平台可能调整部分页面、规则、认证流程和推荐逻辑。
            如果服务临时中断，我们会尽量缩短影响时间，但不保证所有功能始终连续可用。
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">5. 反馈与争议处理</h2>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">
            如果你在使用中遇到问题、对审核或资料处理结果有疑问，可通过设置页中的“意见反馈”提交说明。
            平台会根据你提供的信息进行排查，并在后续版本中持续优化。
          </p>
        </section>
      </main>
    </div>
  )
}
