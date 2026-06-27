'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Sparkles, AlertTriangle, CheckCircle2, Heart, Users, Lightbulb } from 'lucide-react'
import { AudioMessage } from '@/components/her/audio-message'

function renderInline(content: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|==[^=]+==|~~[^~]+~~)/g
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
        <span 
          key={`${match.index}-underline`} 
          className="font-medium text-coral underline decoration-coral/40 decoration-2 underline-offset-2"
        >
          {token.slice(2, -2)}
        </span>,
      )
    } else if (token.startsWith('==') && token.endsWith('==')) {
      nodes.push(
        <span
          key={`${match.index}-highlight`}
          className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-primary/15 to-coral/10 px-2 py-0.5 font-semibold text-primary ring-1 ring-primary/20"
        >
          <Sparkles className="h-3 w-3 text-primary/70" />
          {token.slice(2, -2)}
        </span>,
      )
    } else if (token.startsWith('~~') && token.endsWith('~~')) {
      nodes.push(
        <span
          key={`${match.index}-wave`}
          className="font-medium text-foreground underline decoration-wavy decoration-sage/70 decoration-2 underline-offset-3"
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

// 获取段落类型对应的图标
function getSectionIcon(sectionType: string) {
  switch (sectionType) {
    case 'relationship':
      return <Heart className="h-3.5 w-3.5" />
    case 'match':
      return <Users className="h-3.5 w-3.5" />
    case 'advice':
      return <Lightbulb className="h-3.5 w-3.5" />
    case 'risk':
      return <AlertTriangle className="h-3.5 w-3.5" />
    default:
      return <CheckCircle2 className="h-3.5 w-3.5" />
  }
}

// 检测段落类型
function detectSectionType(line: string): string | null {
  if (/关系画像|关系模式/.test(line)) return 'relationship'
  if (/匹配建议|配对建议/.test(line)) return 'match'
  if (/相处建议|沟通建议/.test(line)) return 'advice'
  if (/风险提醒|注意事项/.test(line)) return 'risk'
  return null
}

function isOpeningLine(line: string): boolean {
  return /^亲爱的[，,]/.test(line)
}

function isTransitionLine(line: string): boolean {
  return /^(再往下说一点|放到关系里|如果再往前多说一步)/.test(line)
}

function isClosingLine(line: string): boolean {
  return /^如果你愿意/.test(line)
}

export function XiaoyaRichText({
  content,
  className,
  mediaType,
  mediaUrl,
  mediaMetadata,
  autoPlayAudio = false,  // 新增：是否自动播放语音
}: {
  content: string
  className?: string
  mediaType?: string
  mediaUrl?: string
  mediaMetadata?: {
    duration_ms?: number
    format?: string
    size?: number
    tts_engine?: string
    voice?: string
  }
  autoPlayAudio?: boolean  // 是否自动播放语音（类似豆包）
}) {
  const lines = content.split('\n').filter((line, index, all) => line.trim() !== '' || (index > 0 && all[index - 1].trim() !== ''))

  return (
    <div className={cn('space-y-3.5 text-[14px] leading-7 text-muted-foreground', className)}>
      {/* 音频消息 - 小喇叭图标，支持自动播放 */}
      {mediaType === 'audio' && mediaUrl && mediaMetadata && (
        <AudioMessage
          audioUrl={mediaUrl}
          durationMs={mediaMetadata.duration_ms}
          format={mediaMetadata.format}
          autoPlay={autoPlayAudio}  // 自动播放（类似豆包）
          className="mb-2"
        />
      )}

      {/* 文本内容 */}
      {lines.map((rawLine, index) => {
        const line = rawLine.trim()

        if (!line) {
          return <div key={`spacer-${index}`} className="h-2" />
        }

        if (isOpeningLine(line)) {
          return (
            <div
              key={`opening-${index}`}
              className="inline-flex items-center rounded-full bg-secondary/70 px-3 py-1 text-[11px] font-medium tracking-[0.08em] text-foreground/80"
            >
              {renderInline(line)}
            </div>
          )
        }

        // 检测是否是章节标题（**xxx**格式且独占一行）
        if (/^\*\*.+\*\*[：:]?$/.test(line)) {
          const sectionType = detectSectionType(line)
          const icon = sectionType ? getSectionIcon(sectionType) : null
          const colorClass = sectionType === 'risk' 
            ? 'bg-rose/10 text-rose border-rose/20' 
            : 'bg-secondary text-foreground border-border'
          
          return (
            <div
              key={`heading-${index}`}
              className={cn(
                "mt-4 mb-2 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold tracking-wide shadow-sm",
                colorClass
              )}
            >
              {icon}
              <span>{line.replace(/^\*\*|\*\*[：:]?$/g, '')}</span>
            </div>
          )
        }

        // 数字列表项
        const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/)
        if (numberedMatch) {
          return (
            <div key={`num-${index}`} className="flex items-start gap-3 pl-1">
              <span className="mt-0.5 inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-primary/10 text-[11px] font-bold text-primary shadow-sm ring-1 ring-primary/15">
                {numberedMatch[1]}
              </span>
              <p className="flex-1 leading-relaxed">{renderInline(numberedMatch[2])}</p>
            </div>
          )
        }

        // 破折号列表项
        const bulletMatch = line.match(/^-+\s+(.+)$/)
        if (bulletMatch) {
          const isRiskLine = /高频风险点|容易卡住|重点磨合|风险/.test(bulletMatch[1])
          const isMatchLine = /高匹配|次高匹配|最佳/.test(bulletMatch[1])
          const isAdviceLine = /为什么适合|为什么容易/.test(bulletMatch[1])
          
          let dotColor = 'bg-primary/60'
          let textClass = ''
          
          if (isRiskLine) {
            dotColor = 'bg-rose'
            textClass = 'text-rose-700'
          } else if (isMatchLine) {
            dotColor = 'bg-sage'
          } else if (isAdviceLine) {
            dotColor = 'bg-coral'
          }
          
          return (
            <div key={`bullet-${index}`} className="flex items-start gap-3 pl-1">
              <span className={cn('mt-2 h-1.5 w-1.5 shrink-0 rounded-full', dotColor)} />
              <p className={cn('flex-1 leading-relaxed', textClass)}>{renderInline(bulletMatch[1])}</p>
            </div>
          )
        }

        // 主要结果行（你这次测出来是...）
        const isPrimaryResult = /你这次测出来是|你这次更偏|你这次整体更偏/.test(line)
        if (isPrimaryResult) {
          return (
            <div
              key={`result-${index}`}
              className="relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/10 via-primary/5 to-transparent px-4 py-3.5 text-foreground shadow-sm"
            >
              <div className="absolute -right-4 -top-4 h-16 w-16 rounded-full bg-primary/10 blur-2xl" />
              <div className="relative flex items-start gap-2">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span className="leading-relaxed">{renderInline(line)}</span>
              </div>
            </div>
          )
        }

        if (isTransitionLine(line)) {
          return (
            <div
              key={`transition-${index}`}
              className="mt-1 rounded-2xl border border-border/70 bg-background/70 px-3.5 py-2.5 text-[13px] font-medium leading-6 text-foreground shadow-sm"
            >
              {renderInline(line)}
            </div>
          )
        }

        // 风险标题行
        const isRiskTitle = /高频风险点|风险提醒/.test(line)
        if (isRiskTitle) {
          return (
            <div
              key={`risk-${index}`}
              className="relative overflow-hidden rounded-2xl border border-rose/25 bg-gradient-to-br from-rose/10 via-rose/5 to-transparent px-4 py-3.5 shadow-sm"
            >
              <div className="absolute -right-4 -top-4 h-16 w-16 rounded-full bg-rose/10 blur-2xl" />
              <div className="relative flex items-start gap-2 text-rose-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="leading-relaxed">{renderInline(line)}</span>
              </div>
            </div>
          )
        }

        if (isClosingLine(line)) {
          return (
            <div
              key={`closing-${index}`}
              className="rounded-2xl bg-secondary/45 px-4 py-3.5 text-[13px] leading-6 text-foreground/85"
            >
              {renderInline(line)}
            </div>
          )
        }

        // 普通段落
        return (
          <p key={`paragraph-${index}`} className="whitespace-pre-wrap leading-7 text-[14px]">
            {renderInline(line)}
          </p>
        )
      })}
    </div>
  )
}
