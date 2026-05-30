'use client'

import { useVerificationFlow } from './use-verification-flow'
import { VerificationSelectStep } from './verification-select-step'
import { VerificationVideoIntro } from './verification-video-intro'
import { VerificationVideoRecord } from './verification-video-record'
import { VerificationVideoReview } from './verification-video-review'
import { VerificationVideoPending } from './verification-video-pending'
import { VerificationFieldUpload } from './verification-field-upload'
import { VerificationFieldPending } from './verification-field-pending'

interface VerificationFlowPageProps {
  onBack: () => void
}

export default function VerificationFlowPage({ onBack }: VerificationFlowPageProps) {
  const {
    fieldVerificationTypes,
    loadError,
    isLoading,
    step,
    setStep,
    selectedField,
    isRecording,
    recordingTime,
    liveChallenge,
    recordedVideo,
    setRecordedVideo,
    isSubmittingVideo,
    selectedFile,
    setSelectedFile,
    isSubmittingField,
    fileInputRef,
    verifiedCount,
    progress,
    directEntry,
    startVideoVerification,
    handleRecordVideo,
    finishVideoSubmission,
    handleStartFieldVerification,
    handleSubmitField,
    getStatusStyles,
    getStatusText,
  } = useVerificationFlow()

  // 选择认证类型页面
  if (step === 'select') {
    return (
      <VerificationSelectStep
        verifiedCount={verifiedCount}
        progress={progress}
        fieldVerificationTypes={fieldVerificationTypes}
        loadError={loadError}
        isLoading={isLoading}
        onBack={onBack}
        onStartVideoVerification={() => setStep('video-intro')}
        onStartFieldVerification={handleStartFieldVerification}
        getStatusStyles={getStatusStyles}
        getStatusText={getStatusText}
      />
    )
  }

  // 视频认证介绍
  if (step === 'video-intro') {
    return (
      <VerificationVideoIntro
        isSubmittingVideo={isSubmittingVideo}
        liveChallenge={liveChallenge}
        onBack={directEntry ? onBack : () => setStep('select')}
        onStartVideoVerification={() => void startVideoVerification()}
      />
    )
  }

  // 视频录制
  if (step === 'video-record') {
    return (
      <VerificationVideoRecord
        isRecording={isRecording}
        recordingTime={recordingTime}
        onBack={() => setStep('video-intro')}
        onRecordVideo={handleRecordVideo}
      />
    )
  }

  // 视频预览确认
  if (step === 'video-review') {
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

  // 视频提交成功
  if (step === 'video-pending') {
    return <VerificationVideoPending onBack={onBack} />
  }

  // 文件上传
  if (step === 'field-upload') {
    return (
      <VerificationFieldUpload
        selectedField={selectedField}
        fieldVerificationTypes={fieldVerificationTypes}
        selectedFile={selectedFile}
        isSubmittingField={isSubmittingField}
        fileInputRef={fileInputRef}
        onBack={directEntry ? onBack : () => setStep('select')}
        onFileSelect={setSelectedFile}
        onSubmit={handleSubmitField}
      />
    )
  }

  // 文件提交成功
  if (step === 'field-pending') {
    return <VerificationFieldPending onBack={onBack} />
  }

  return null
}
