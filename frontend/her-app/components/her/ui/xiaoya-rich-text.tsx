'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

function renderInline(content: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|==[^=]+==)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(content)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(content.slice(lastIndex, match.index))
    }

    const token = match[0]
    if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(
        <strong key={`${match.index}-strong`} className="font-semibold text-foreground">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('__') && token.endsWith('__')) {
      nodes.push(
        <span key={`${match.index}-underline`} className="font-medium underline decoration-2 underline-offset-2">
          {token.slice(2, -2)}
        </span>,
      )
    } else if (token.startsWith('==') && token.endsWith('==')) {
      nodes.push(
        <span
          key={`${match.index}-highlight`}
          className="rounded-md bg-primary/15 px-1.5 py-0.5 font-semibold text-primary"
        >
          {token.slice(2, -2)}
        </span>,
      )
    }

    lastIndex = match.index + token.length
  }

  if (lastIndex < content.length) {
    nodes.push(content.slice(lastIndex))
  }

  return nodes
}

export function XiaoyaRichText({
  content,
  className,
}: {
  content: string
  className?: string
}) {
  const lines = content.split('\n').filter((line, index, all) => line.trim() !== '' || (index > 0 && all[index - 1].trim() !== ''))

  return (
    <div className={cn('space-y-2.5 text-sm leading-6 text-muted-foreground', className)}>
      {lines.map((rawLine, index) => {
        const line = rawLine.trim()

        if (!line) {
          return <div key={`spacer-${index}`} className="h-1.5" />
        }

        if (/^\*\*.+\*\*$/.test(line)) {
          return (
            <div
              key={`heading-${index}`}
              className="inline-flex rounded-full bg-secondary px-2.5 py-1 text-[11px] font-semibold tracking-wide text-foreground"
            >
              {renderInline(line)}
            </div>
          )
        }

        const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/)
        if (numberedMatch) {
          return (
            <div key={`num-${index}`} className="flex items-start gap-2.5">
              <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary/12 px-1.5 text-[11px] font-semibold text-primary">
                {numberedMatch[1]}
              </span>
              <p className="flex-1">{renderInline(numberedMatch[2])}</p>
            </div>
          )
        }

        const bulletMatch = line.match(/^-+\s+(.+)$/)
        if (bulletMatch) {
          const isRiskLine = /高频风险点|容易卡住|重点磨合/.test(bulletMatch[1])
          return (
            <div key={`bullet-${index}`} className="flex items-start gap-2.5">
              <span className={cn('mt-2 h-1.5 w-1.5 rounded-full bg-primary/70', isRiskLine && 'bg-rose')} />
              <p className={cn('flex-1', isRiskLine && 'text-rose-700')}>{renderInline(bulletMatch[1])}</p>
            </div>
          )
        }

        const isPrimaryResult = /你这次测出来是|你这次更偏|你最主要的恋爱语言是|你这次整体更偏/.test(line)
        const isRiskTitle = /高频风险点|风险提醒/.test(line)

        if (isPrimaryResult) {
          return (
            <div
              key={`result-${index}`}
              className="rounded-2xl border border-primary/15 bg-primary/10 px-3.5 py-3 text-foreground shadow-sm"
            >
              {renderInline(line)}
            </div>
          )
        }

        if (isRiskTitle) {
          return (
            <div
              key={`risk-${index}`}
              className="rounded-2xl border border-rose/20 bg-rose/10 px-3.5 py-3 text-rose-700"
            >
              {renderInline(line)}
            </div>
          )
        }

        return (
          <p key={`paragraph-${index}`} className="whitespace-pre-wrap">
            {renderInline(line)}
          </p>
        )
      })}
    </div>
  )
}
