'use client'

import { useState, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'

// 设置PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`

type PDFPreviewProps = {
  fileUrl: string
  className?: string
}

export function PDFPreview({ fileUrl, className }: PDFPreviewProps) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageNumber, setPageNumber] = useState<number>(1)
  const [scale, setScale] = useState<number>(1.0)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  // 加载PDF文档
  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages)
    setLoading(false)
    setError(null)
  }

  // 加载失败
  const onDocumentLoadError = (error: Error) => {
    setLoading(false)
    setError(error.message || 'PDF加载失败')
  }

  // 页面导航
  const goToPrevPage = () => setPageNumber(Math.max(1, pageNumber - 1))
  const goToNextPage = () => setPageNumber(Math.min(numPages, pageNumber + 1))

  // 缩放控制
  const zoomIn = () => setScale(Math.min(2.0, scale + 0.2))
  const zoomOut = () => setScale(Math.max(0.5, scale - 0.2))

  // 下载PDF
  const handleDownload = () => {
    const link = document.createElement('a')
    link.href = fileUrl
    link.download = 'document.pdf'
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  // 重置状态
  useEffect(() => {
    setPageNumber(1)
    setScale(1.0)
    setLoading(true)
    setError(null)
  }, [fileUrl])

  if (error) {
    return (
      <div className={cn('flex flex-col items-center justify-center min-h-[400px] bg-muted/30 rounded-xl', className)}>
        <FileText className="w-12 h-12 text-muted-foreground mb-4" />
        <p className="text-sm text-muted-foreground mb-4">PDF加载失败</p>
        <button
          type="button"
          onClick={handleDownload}
          className="rounded-xl border border-border px-4 py-2 text-sm hover:bg-muted/30 transition-colors"
        >
          <Download className="w-4 h-4 inline mr-2" />
          下载查看
        </button>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col', className)}>
      {/* PDF显示区域 */}
      <div className="relative flex items-center justify-center bg-muted/30 rounded-xl overflow-hidden min-h-[400px]">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-sm text-muted-foreground">加载PDF...</div>
          </div>
        )}

        <Document
          file={fileUrl}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading=""
        >
          <Page
            pageNumber={pageNumber}
            scale={scale}
            className="shadow-lg"
            renderTextLayer={false}
            renderAnnotationLayer={false}
          />
        </Document>
      </div>

      {/* 控制栏 */}
      {numPages > 0 && (
        <div className="mt-3 flex items-center justify-between">
          {/* 页面导航 */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={goToPrevPage}
              disabled={pageNumber <= 1}
              className="rounded-lg border border-border p-2 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-muted/30 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-muted-foreground">
              {pageNumber} / {numPages}
            </span>
            <button
              type="button"
              onClick={goToNextPage}
              disabled={pageNumber >= numPages}
              className="rounded-lg border border-border p-2 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-muted/30 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* 缩放控制 */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={zoomOut}
              disabled={scale <= 0.5}
              className="rounded-lg border border-border p-2 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-muted/30 transition-colors"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <span className="text-sm text-muted-foreground">{Math.round(scale * 100)}%</span>
            <button
              type="button"
              onClick={zoomIn}
              disabled={scale >= 2.0}
              className="rounded-lg border border-border p-2 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-muted/30 transition-colors"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
          </div>

          {/* 下载按钮 */}
          <button
            type="button"
            onClick={handleDownload}
            className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted/30 transition-colors"
          >
            <Download className="w-4 h-4 inline mr-1" />
            下载
          </button>
        </div>
      )}
    </div>
  )
}