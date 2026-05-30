'use client'

import { CheckCircle } from 'lucide-react'
import { PageTransition } from '@/components/her/ui/animations'

interface VerificationFieldPendingProps {
  onBack: () => void
}

export function VerificationFieldPending({ onBack }: VerificationFieldPendingProps) {
  return (
    <PageTransition className="min-h-screen bg-background max-w-md mx-auto flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3">
          <h1 className="font-medium text-foreground">提交成功</h1>
        </div>
      </header>

      <div className="flex-1 flex flex-col items-center justify-center px-8 text-center">
        <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-6">
          <CheckCircle className="w-8 h-8 text-primary" />
        </div>

        <h2 className="font-serif text-xl text-foreground mb-3">材料已提交</h2>
        <p className="text-sm text-muted-foreground mb-2">
          感谢你的配合
        </p>
        <p className="text-sm text-muted-foreground mb-8">
          我们会在1-2个工作日内完成审核
        </p>

        <button
          onClick={onBack}
          className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium"
        >
          返回
        </button>
      </div>
    </PageTransition>
  )
}