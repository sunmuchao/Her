'use client'

import { useId, useMemo, useRef, useState, type ChangeEvent } from 'react'
import Image from 'next/image'
import { Camera, Loader2, Sparkles, Star, Upload, UserRoundSearch } from 'lucide-react'

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
      setStatusText('图片准备好了，可以开始搜索')
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

  return (
    <section className="rounded-3xl border border-border/70 bg-card/95 p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">上传图片搜索</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{statusText}</p>
        </div>
        <div className="rounded-2xl bg-primary/10 p-2 text-primary">
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
                setStatusText('模式已切换，继续补图片或文字描述就行。')
              }}
              className={cn(
                'rounded-2xl border px-3 py-2 text-left transition-colors',
                active
                  ? 'border-primary/40 bg-primary/10 text-primary'
                  : 'border-border bg-background text-muted-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              <div className="mt-1 text-xs font-medium">{item.label}</div>
            </button>
          )
        })}
      </div>

      <div className="mt-4 space-y-3">
        {mode !== 'celebrity' ? (
          <>
            <div className="flex items-center gap-3">
              <input
                ref={fileInputRef}
                id={inputId}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/*"
                className="hidden"
                onChange={handleFileChange}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-2 rounded-2xl border border-dashed border-primary/35 bg-primary/5 px-3 py-2 text-sm text-primary"
              >
                <Upload className="h-4 w-4" />
                选一张图片
              </button>
              <span className="text-xs text-muted-foreground">支持 JPG / PNG / WEBP，自动压缩</span>
            </div>

            {imagePreview ? (
              <div className="relative h-40 overflow-hidden rounded-2xl border border-border bg-secondary/40">
                <Image src={imagePreview} alt="已上传参考图" fill className="object-cover" unoptimized />
              </div>
            ) : null}

            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">或者直接贴图片地址</span>
              <input
                value={imageSource}
                onChange={(event) => {
                  setImageSource(event.target.value)
                  if (!imagePreview) setStatusText('已填图片地址，可以直接开始搜索')
                }}
                placeholder="https://..."
                className="w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-primary/40"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">
                {mode === 'face' ? '补充说明，可不填' : '再说一下你想找的感觉，可不填'}
              </span>
              <input
                value={queryText}
                onChange={(event) => setQueryText(event.target.value)}
                placeholder={mode === 'face' ? '比如：笑起来像这张、五官更清秀' : '比如：清爽、自然、温柔、有少年感'}
                className="w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-primary/40"
              />
            </label>
          </>
        ) : (
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">输入明星名字</span>
            <input
              value={celebrityName}
              onChange={(event) => setCelebrityName(event.target.value)}
              placeholder="比如：刘亦菲、田曦薇、金城武"
              className="w-full rounded-2xl border border-border bg-background px-3 py-2 text-sm outline-none transition-colors focus:border-primary/40"
            />
          </label>
        )}
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
          {mode === 'face' ? '更适合找“长得像”' : mode === 'style' ? '更适合找“感觉像”' : '更适合找“像某明星”'}
        </div>
        <button
          type="button"
          disabled={!canSearch || stage === 'searching'}
          onClick={() => void handleSearch()}
          className="inline-flex min-w-28 items-center justify-center gap-2 rounded-2xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {stage === 'searching' ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          开始搜索
        </button>
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
