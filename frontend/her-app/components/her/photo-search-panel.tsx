'use client'

import { useId, useMemo, useRef, useState, type ChangeEvent } from 'react'
import Image from 'next/image'
import { Camera, ImagePlus, Loader2, Send, Sparkles, Star, UserRoundSearch, X } from 'lucide-react'

import { DiscoveryCandidateCard } from './discovery-candidate-card'
import { searchDiscoveryByPhoto, type DiscoveryPhotoSearchMode } from '@/lib/api/endpoints/discovery'
import { notifyError } from '@/lib/notify'
import { cn } from '@/lib/utils'
import type { CandidatePreview } from '@/lib/types/candidate'

type PhotoSearchPanelProps = {
  profileId: number | null
  onViewCandidate: (candidateId: string, candidate?: CandidatePreview, sessionId?: string | null) => void
}

type SearchStage = 'idle' | 'validating' | 'compressing' | 'searching' | 'done' | 'error'

const ACCEPTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const MAX_IMAGE_BYTES = 10 * 1024 * 1024

async function compressImage(file: File, maxWidth = 1280, quality = 0.82): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (event) => {
      const img = new window.Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        let width = img.width
        let height = img.height
        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width)
          width = maxWidth
        }
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          reject(new Error('图片预处理失败'))
          return
        }
        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.onerror = () => reject(new Error('图片解析失败'))
      img.src = String(event.target?.result || '')
    }
    reader.onerror = () => reject(new Error('图片读取失败'))
    reader.readAsDataURL(file)
  })
}

export function PhotoSearchPanel({ profileId, onViewCandidate }: PhotoSearchPanelProps) {
  const inputId = useId()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [mode, setMode] = useState<DiscoveryPhotoSearchMode>('face')
  const [queryText, setQueryText] = useState('')
  const [celebrityName, setCelebrityName] = useState('')
  const [imageSource, setImageSource] = useState('')
  const [imagePreview, setImagePreview] = useState('')
  const [stage, setStage] = useState<SearchStage>('idle')
  const [statusText, setStatusText] = useState('传一张图，我帮你找像这张脸、这种感觉或像某个明星的人。')
  const [results, setResults] = useState<CandidatePreview[]>([])

  const stageIndex = useMemo(() => {
    const order: SearchStage[] = ['idle', 'validating', 'compressing', 'searching', 'done', 'error']
    return order.indexOf(stage)
  }, [stage])

  const modes = [
    { key: 'face' as const, label: '找像这张脸', icon: UserRoundSearch },
    { key: 'style' as const, label: '找这种感觉', icon: Sparkles },
    { key: 'celebrity' as const, label: '像某明星', icon: Star },
  ]

  const canSearch =
    typeof profileId === 'number' &&
    profileId > 0 &&
    (mode === 'celebrity'
      ? Boolean(celebrityName.trim())
      : Boolean(imageSource.trim()))

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      setStage('validating')
      setStatusText('先检查图片格式和大小')
      if (!ACCEPTED_IMAGE_TYPES.has(file.type)) {
        throw new Error('目前只支持 JPG、PNG、WEBP')
      }
      if (file.size > MAX_IMAGE_BYTES) {
        throw new Error('图片不能超过 10MB')
      }
      setStage('compressing')
      setStatusText('正在压缩图片，避免上传太慢')
      const compressed = await compressImage(file)
      setImageSource(compressed)
      setImagePreview(compressed)
      setStage('idle')
      setStatusText('图片已经选好，像微信发图一样，点右侧发送就行')
    } catch (error) {
      setStage('error')
      setStatusText(error instanceof Error ? error.message : '图片处理失败')
      notifyError(error, '图片处理失败')
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleSearch = async () => {
    if (!profileId || !canSearch) return
    setStage('searching')
    setStatusText(
      mode === 'face'
        ? '正在找像这张脸的人'
        : mode === 'style'
          ? '正在找同一种感觉的人'
          : `正在找像 ${celebrityName.trim()} 的人`,
    )
    try {
      const response = await searchDiscoveryByPhoto({
        profileId,
        mode,
        imageSource: mode === 'celebrity' ? undefined : imageSource,
        queryText: mode === 'celebrity' ? celebrityName.trim() : queryText.trim(),
        celebrityName: mode === 'celebrity' ? celebrityName.trim() : undefined,
        topK: 12,
      })
      setResults(response.results || [])
      setStage('done')
      setStatusText(
        response.result_count
          ? `找到了 ${response.result_count} 个可继续看的候选人`
          : '这次没找到合适的人，换一张图或换个模式再试试',
      )
    } catch (error) {
      setStage('error')
      setStatusText('搜索失败，请稍后再试')
      notifyError(error, '照片搜索失败')
    }
  }

  const clearSelectedImage = () => {
    setImageSource('')
    setImagePreview('')
    setResults([])
    setStage('idle')
    setStatusText('重新选一张图，或者换个模式再发一次。')
  }

  const composerPlaceholder =
    mode === 'face'
      ? '补一句，比如 笑起来像这张、五官更清秀'
      : mode === 'style'
        ? '补一句，比如 清爽、自然、温柔、有少年感'
        : '输入明星名字，比如 刘亦菲、田曦薇'

  return (
    <section className="rounded-[2rem] border border-border/70 bg-[linear-gradient(180deg,rgba(253,242,248,0.96),rgba(255,255,255,0.98))] p-4 shadow-[0_18px_40px_rgba(131,24,67,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">发一张图搜人</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{statusText}</p>
        </div>
        <div className="rounded-2xl bg-primary/10 p-2 text-primary shadow-sm">
          <Camera className="h-4 w-4" />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        {modes.map((item) => {
          const Icon = item.icon
          const active = mode === item.key
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setMode(item.key)
                setResults([])
                setStatusText(item.key === 'celebrity' ? '直接输入明星名字再发送。' : '继续选图，像发微信图片一样发出去。')
              }}
              className={cn(
                'rounded-2xl border px-3 py-2 text-left transition-colors',
                active
                  ? 'border-primary/40 bg-white/90 text-primary shadow-sm'
                  : 'border-white/80 bg-white/55 text-muted-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              <div className="mt-1 text-xs font-medium">{item.label}</div>
            </button>
          )
        })}
      </div>

      <input
        ref={fileInputRef}
        id={inputId}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/*"
        className="hidden"
        onChange={handleFileChange}
      />

      <div className="mt-4 rounded-[1.75rem] border border-white/80 bg-white/80 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)]">
        {mode !== 'celebrity' ? (
          <>
            {imagePreview ? (
              <div className="mb-3 flex items-start gap-3 rounded-3xl bg-secondary/40 p-2.5">
                <div className="relative h-16 w-16 overflow-hidden rounded-2xl border border-white/80 bg-white">
                  <Image src={imagePreview} alt="已选参考图" fill className="object-cover" unoptimized />
                </div>
                <div className="min-w-0 flex-1 pt-1">
                  <p className="text-sm font-medium text-foreground">已选参考图</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    这一步就像微信里图片已经挂在输入框上，补一句话再发送即可。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={clearSelectedImage}
                  className="rounded-full bg-white p-2 text-muted-foreground transition-colors hover:text-foreground"
                  aria-label="移除已选图片"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="mb-3 flex w-full items-center gap-3 rounded-3xl border border-dashed border-primary/30 bg-primary/5 px-4 py-3 text-left transition-colors hover:bg-primary/10"
              >
                <div className="rounded-2xl bg-white p-2 text-primary shadow-sm">
                  <ImagePlus className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">选一张参考图</p>
                  <p className="mt-1 text-xs text-muted-foreground">支持 JPG / PNG / WEBP，选完后会先压缩再发送</p>
                </div>
              </button>
            )}
          </>
        ) : null}

        <div className="flex items-center gap-2 rounded-[1.5rem] bg-[#fff7fb] px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
          {mode !== 'celebrity' ? (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-primary shadow-sm transition-transform hover:scale-[1.03]"
              aria-label="选择图片"
            >
              <ImagePlus className="h-5 w-5" />
            </button>
          ) : (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-primary shadow-sm">
              <Star className="h-5 w-5" />
            </div>
          )}

          <input
            value={mode === 'celebrity' ? celebrityName : queryText}
            onChange={(event) => {
              if (mode === 'celebrity') {
                setCelebrityName(event.target.value)
                return
              }
              setQueryText(event.target.value)
            }}
            placeholder={composerPlaceholder}
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />

          <button
            type="button"
            disabled={!canSearch || stage === 'searching'}
            onClick={() => void handleSearch()}
            className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-full bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm transition-transform disabled:opacity-50"
          >
            {stage === 'searching' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            <span className="hidden sm:inline">{mode === 'celebrity' ? '发送名字' : '发送图片'}</span>
          </button>
        </div>

        {mode !== 'celebrity' ? (
          <div className="mt-2 px-1 text-[11px] leading-5 text-muted-foreground">
            也可以直接贴图片地址：
            <button
              type="button"
              onClick={() => {
                const next = window.prompt('贴入图片地址')
                if (!next) return
                setImageSource(next)
                setImagePreview('')
                setStatusText('图片地址已经挂上，点发送开始搜索。')
              }}
              className="ml-1 text-primary underline underline-offset-2"
            >
              粘贴 URL
            </button>
          </div>
        ) : null}
      </div>

      <div className="mt-4 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className={cn('rounded-full px-2 py-1', stageIndex >= 1 ? 'bg-primary/10 text-primary' : 'bg-secondary')}>
          1. 校验
        </span>
        <span className={cn('rounded-full px-2 py-1', stageIndex >= 2 ? 'bg-primary/10 text-primary' : 'bg-secondary')}>
          2. 预处理
        </span>
        <span className={cn('rounded-full px-2 py-1', stageIndex >= 3 ? 'bg-primary/10 text-primary' : 'bg-secondary')}>
          3. 搜索
        </span>
        <span className={cn('rounded-full px-2 py-1', stageIndex >= 4 && stage !== 'error' ? 'bg-primary/10 text-primary' : 'bg-secondary')}>
          4. 出结果
        </span>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="text-xs text-muted-foreground">
          {mode === 'face' ? '像发一张脸照去找相似款' : mode === 'style' ? '像发一张氛围图去找同感觉' : '直接输入名字找明星脸'}
        </div>
        <span className="rounded-full bg-white/80 px-2.5 py-1 text-[11px] text-primary shadow-sm">
          微信式发图交互
        </span>
      </div>

      {results.length > 0 ? (
        <div className="mt-5 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">搜索结果</p>
            <span className="text-xs text-muted-foreground">{results.length} 人</span>
          </div>
          {results.map((candidate, index) => (
            <DiscoveryCandidateCard
              key={`photo-search-${candidate.id}-${index}`}
              candidate={candidate}
              onViewCandidate={onViewCandidate}
              className="animate-fade-in-up"
              style={{ animationDelay: `${Math.min(index, 6) * 50}ms` }}
            />
          ))}
        </div>
      ) : null}
    </section>
  )
}
