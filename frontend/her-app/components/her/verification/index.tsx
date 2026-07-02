'use client'

import { Suspense } from 'react'
import { useVerificationFlow } from './use-verification-flow'
import { VerificationVideoIntro } from './verification-video-intro'
import { VerificationVideoRecord } from './verification-video-record'
import { VerificationVideoReview } from './verification-video-review'
import { VerificationVideoPending } from './verification-video-pending'
import { VerificationFieldUpload } from './verification-field-upload'
import { VerificationFieldPending } from './verification-field-pending'

interface VerificationFlowPageProps {
  onBack: () => void
}

function VerificationFlowContent({ onBack }: VerificationFlowPageProps) {
  console.log('[VerificationFlowContent] 开始渲染')

  const {
    fieldVerificationTypes,
    loadError,
    step,
    setStep,
    selectedField,
    isRecording,
    recordingTime,
    liveChallenge,
    recordedVideo,
    previewStream,
    setRecordedVideo,
    isSubmittingVideo,
    selectedFile,
    setSelectedFile,
    isSubmittingField,
    fileInputRef,
    handleDirectBack,
    startVideoVerification,
    handleRecordVideo,
    finishVideoSubmission,
    handleSubmitField,
  } = useVerificationFlow(onBack)

  console.log('[VerificationFlowContent] useVerificationFlow 返回值:', {
    loadError,
    step,
    selectedField,
    fieldVerificationTypesLength: fieldVerificationTypes?.length,
  })

  if (loadError) {
    console.log('[VerificationFlowContent] 显示错误页面:', loadError)
    return (
      <div className="h-full bg-background flex items-center justify-center px-6 text-center">
        <div>
          <p className="text-sm text-muted-foreground mb-4">{loadError}</p>
          <button
            type="button"
            onClick={onBack}
            className="rounded-xl bg-primary px-4 py-3 text-sm font-medium text-primary-foreground"
          >
            返回
          </button>
        </div>
      </div>
    )
  }

  console.log('[VerificationFlowContent] 当前 step:', step)

  if (step === 'video-intro') {
    console.log('[VerificationFlowContent] 渲染 video-intro')
    return (
      <VerificationVideoIntro
        isSubmittingVideo={isSubmittingVideo}
        liveChallenge={liveChallenge}
        onBack={handleDirectBack}
        onStartVideoVerification={() => void startVideoVerification()}
      />
    )
  }

  if (step === 'video-record') {
    console.log('[VerificationFlowContent] 渲染 video-record')
    return (
      <VerificationVideoRecord
        isRecording={isRecording}
        recordingTime={recordingTime}
        previewStream={previewStream}
        onBack={() => setStep('video-intro')}
        onRecordVideo={handleRecordVideo}
      />
    )
  }

  if (step === 'video-review') {
    console.log('[VerificationFlowContent] 渲染 video-review')
    return (
      <VerificationVideoReview
        recordedVideo={recordedVideo}
        isSubmittingVideo={isSubmittingVideo}
        onBack={() => setStep('video-record')}
        onSubmit={finishVideoSubmission}
        onRerecord={() => {
          setRecordedVideo(null)
          setStep('video-record')
        }}
      />
    )
  }

  if (step === 'video-pending') {
    console.log('[VerificationFlowContent] 渲染 video-pending')
    return <VerificationVideoPending onBack={onBack} />
  }

  if (step === 'field-upload') {
    console.log('[VerificationFlowContent] 渲染 field-upload')
    return (
      <VerificationFieldUpload
        selectedField={selectedField}
        fieldVerificationTypes={fieldVerificationTypes}
        selectedFile={selectedFile}
        isSubmittingField={isSubmittingField}
        fileInputRef={fileInputRef}
        onBack={handleDirectBack}
        onFileSelect={setSelectedFile}
        onSubmit={handleSubmitField}
      />
    )
  }

  if (step === 'field-pending') {
    console.log('[VerificationFlowContent] 渲染 field-pending')
    return <VerificationFieldPending onBack={onBack} />
  }

  console.log('[VerificationFlowContent] 没有匹配的 step，返回 null')
  return null
}

export default function VerificationFlowPage({ onBack }: VerificationFlowPageProps) {
  console.log('[VerificationFlowPage] 开始渲染，onBack:', typeof onBack)

  return (
    <Suspense fallback={
      <div className="h-full bg-background flex items-center justify-center">
        <div className="text-sm text-muted-foreground">加载中...</div>
      </div>
    }>
      <VerificationFlowContent onBack={onBack} />
    </Suspense>
  )
}
