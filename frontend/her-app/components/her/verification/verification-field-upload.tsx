'use client'

import { ArrowLeft, Upload, AlertCircle } from 'lucide-react'
import { useRef } from 'react'
import { PageTransition } from '@/components/her/ui/animations'
import type { FieldItem } from './use-verification-flow'

interface VerificationFieldUploadProps {
  selectedField: string | null
  fieldVerificationTypes: FieldItem[]
  selectedFile: File | null
  isSubmittingField: boolean
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onBack: () => void
  onFileSelect: (file: File | null) => void
  onSubmit: () => void
}

export function VerificationFieldUpload({
  selectedField,
  fieldVerificationTypes,
  selectedFile,
  isSubmittingField,
  fileInputRef,
  onBack,
  onFileSelect,
  onSubmit,
}: VerificationFieldUploadProps) {
  const field = fieldVerificationTypes.find((f) => f.id === selectedField)
  const internalFileInputRef = useRef<HTMLInputElement>(null)
  const activeRef = fileInputRef?.current ? fileInputRef : internalFileInputRef

  return (
    <PageTransition className="h-full bg-background flex flex-col">
      <header className="sticky top-0 z-20 bg-background border-b border-border safe-area-top">
        <div className="px-4 py-3 flex items-center gap-3">
          <button onClick={onBack} className="w-10 h-10 rounded-full hover:bg-secondary flex items-center justify-center transition-colors">
            <ArrowLeft className="w-5 h-5 text-foreground" />
          </button>
          <h1 className="font-medium text-foreground">{field?.name}</h1>
        </div>
      </header>
      <div className="flex-1 px-5 py-6">
        <p className="text-sm text-muted-foreground mb-6">{field?.description}，我们会在1-2个工作日内完成审核。</p>
        <input
          ref={activeRef}
          type="file"
          accept="image/jpeg,image/png,application/pdf"
          className="hidden"
          onChange={(event) => onFileSelect(event.target.files?.[0] || null)}
        />
        <button
          type="button"
          onClick={() => activeRef?.current?.click()}
          className="w-full border-2 border-dashed border-border rounded-xl p-8 text-center mb-6 hover:border-primary/30 transition-colors"
        >
          <div className="w-14 h-14 rounded-full bg-secondary mx-auto flex items-center justify-center mb-4">
            <Upload className="w-7 h-7 text-muted-foreground" />
          </div>
          <p className="text-sm text-foreground mb-2">{selectedFile ? selectedFile.name : '点击选择文件上传'}</p>
          <p className="text-xs text-muted-foreground">支持 JPG、PNG、PDF 格式，最大10MB</p>
        </button>
        <div className="bg-secondary/50 rounded-xl p-4 mb-6">
          <h4 className="text-sm font-medium text-foreground mb-2 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-primary" />
            注意事项
          </h4>
          <ul className="text-xs text-muted-foreground space-y-1">
            <li>• 请确保上传的文件清晰可读</li>
            <li>• 敏感信息可以打码处理</li>
            <li>• 信息仅用于认证，不会对外展示</li>
          </ul>
        </div>
        <button
          onClick={() => void onSubmit()}
          disabled={isSubmittingField || !selectedFile}
          className="w-full py-4 bg-primary rounded-2xl text-primary-foreground font-medium disabled:opacity-60"
        >
          {isSubmittingField ? '提交中…' : '提交审核'}
        </button>
      </div>
    </PageTransition>
  )
}
