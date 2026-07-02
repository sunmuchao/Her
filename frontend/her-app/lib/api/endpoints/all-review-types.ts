import { gatewayJson } from '@/lib/api/client'

// ==================== 活体视频认证审核 ====================

export type VideoSubmission = {
  submission_id: string
  user_id: string
  profile_id: number
  video_url: string
  status: 'submitted' | 'under_review' | 'approved' | 'rejected'
  submitted_at: string
  challenges?: string[] // 挑战动作列表（点头、眨眼等）
  liveness_result?: {
    passed: boolean
    score?: number
  }
  face_match_result?: {
    matched: boolean
    similarity?: number
  }
}

export type VideoReviewParams = {
  submissionId: string
  decision: 'approve' | 'reject'
  reviewNote?: string
}

/**
 * 获取活体视频审核队列
 */
export async function fetchVideoReviewQueue(): Promise<{ submissions: VideoSubmission[] }> {
  const response = await gatewayJson<{ submissions?: VideoSubmission[] }>(
    '/v1/verifications/live-video-submissions',
    { includeAuth: true },
  )
  return { submissions: response.submissions || [] }
}

/**
 * 审核活体视频认证
 */
export async function reviewVideoVerification(params: VideoReviewParams): Promise<{ submission: VideoSubmission }> {
  return gatewayJson<{ submission: VideoSubmission }>(
    `/v1/verifications/live-video-submissions/${params.submissionId}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        decision: params.decision,
        review_note: params.reviewNote,
      }),
    },
  )
}

// ==================== 举报审核 ====================

export type ReportCase = {
  case_id: string
  reporter_user_id: string
  reported_user_id: string
  reported_profile_id: number
  report_reason: 'harassment' | 'fraud' | 'fake_profile' | 'inappropriate_behavior' | 'other'
  report_reason_text?: string
  evidence?: string[] // 举报证据URL列表
  status: 'open' | 'under_review' | 'resolved' | 'dismissed'
  created_at: string
}

export type ReportReviewParams = {
  caseId: string
  decision: 'valid' | 'invalid' | 'need_evidence'
  penalty?: 'warning' | 'ban_3d' | 'ban_7d' | 'ban_permanent' | 'unban'
  reviewNote?: string
}

/**
 * 获取举报审核队列
 */
export async function fetchReportReviewQueue(): Promise<{ cases: ReportCase[] }> {
  const response = await gatewayJson<{ cases?: ReportCase[] }>(
    '/v1/profile-review/risk-cases',
    { includeAuth: true },
  )
  return { cases: response.cases || [] }
}

/**
 * 审核举报案例
 */
export async function reviewReportCase(params: ReportReviewParams): Promise<{ case: ReportCase }> {
  return gatewayJson<{ case: ReportCase }>(
    `/v1/profile-review/risk-cases/${params.caseId}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify(params),
    },
  )
}

// ==================== 照片风险审核 ====================

export type PhotoRiskItem = {
  photo_id: string
  profile_id: number
  photo_url: string
  risk_score: number // AI风险评分0-100
  risk_level: 'low' | 'medium' | 'high'
  ai_detection?: {
    is_synthetic?: boolean // 是否合成
    is_stolen?: boolean // 是否盗用
    confidence?: number
  }
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}

export type PhotoRiskReviewParams = {
  photoId: string
  decision: 'real' | 'synthetic' | 'stolen' | 'other'
  reviewNote?: string
}

/**
 * 获取照片风险审核队列
 */
export async function fetchPhotoRiskQueue(): Promise<{ photos: PhotoRiskItem[] }> {
  const response = await gatewayJson<{ photos?: PhotoRiskItem[] }>(
    '/v1/profile-review/photo-risk/review-queue',
    { includeAuth: true },
  )
  return { photos: response.photos || [] }
}

/**
 * 审核照片风险
 */
export async function reviewPhotoRisk(params: PhotoRiskReviewParams): Promise<{ photo: PhotoRiskItem }> {
  return gatewayJson<{ photo: PhotoRiskItem }>(
    `/v1/profile-review/photo-risk/${params.photoId}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify(params),
    },
  )
}

// ==================== 申诉审核 ====================

export type AppealCase = {
  appeal_id: string
  case_id: string // 原处罚案例ID
  user_id: string
  profile_id: number
  appeal_reason: string
  appeal_evidence?: string[] // 申诉证据URL列表
  original_penalty: string // 原处罚措施
  status: 'submitted' | 'under_review' | 'accepted' | 'rejected'
  created_at: string
}

export type AppealReviewParams = {
  appealId: string
  decision: 'accept' | 'reject'
  result?: 'unban' | 'maintain'
  reviewNote?: string
}

/**
 * 获取申诉审核队列
 */
export async function fetchAppealReviewQueue(): Promise<{ appeals: AppealCase[] }> {
  const response = await gatewayJson<{ appeals?: AppealCase[] }>(
    '/v1/profile-review/case-appeals',
    { includeAuth: true },
  )
  return { appeals: response.appeals || [] }
}

/**
 * 审核申诉案例
 */
export async function reviewAppealCase(params: AppealReviewParams): Promise<{ appeal: AppealCase }> {
  return gatewayJson<{ appeal: AppealCase }>(
    `/v1/profile-review/case-appeals/${params.appealId}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify(params),
    },
  )
}