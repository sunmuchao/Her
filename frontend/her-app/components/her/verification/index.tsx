'use client'

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

export default function VerificationFlowPage({ onBack }: VerificationFlowPageProps) {
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

  if (loadError) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-6 text-center">
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

  if (step === 'video-intro') {
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
    return (
      <VerificationVideoRecord
        isRecording={isRecording}
        recordingTime={recordingTime}
        onBack={() => setStep('video-intro')}
        onRecordVideo={handleRecordVideo}
      />
    )
  }

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

  if (step === 'video-pending') {
    return <VerificationVideoPending onBack={onBack} />
  }

  if (step === 'field-upload') {
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
    return <VerificationFieldPending onBack={onBack} />
  }

  return null
}
