import { gatewayJson, queryString } from '@/lib/api/client'
import { getProfileId, getUserId } from '@/lib/auth/session'

// ==================== 类型定义 ====================

export type FieldVerificationSubmission = {
  submission_id?: string
  field_key?: string
  status?: string
  profile_id?: number
}

// 审核相关类型
export type VerificationEvidence = {
  evidence_id?: string
  evidence_type?: 'document_upload' | 'authority_lookup' | 'self_declared'
  evidence_channel?: string
  file_url?: string
  file_type?: 'image/jpeg' | 'image/png' | 'application/pdf'
  extracted_data?: Record<string, string>
  confidence_score?: number
}

export type VerificationReview = {
  review_id: string
  submission_id: string
  reviewer_id: string
  decision: 'approve' | 'reject' | 'request_resubmission'
  review_note?: string
  approved_value?: string
  requested_documents?: string[]
  reviewed_at: string
  created_at?: string
}

export type VerificationSubmissionDetail = {
  submission_id: string
  profile_id: number
  user_id?: string
  field_key: 'education' | 'job' | 'income'
  declared_value: string
  status: 'submitted' | 'under_review' | 'approved' | 'rejected' | 'resubmission_required'
  evidence: VerificationEvidence[]
  created_at?: string  // 创建时间
  updated_at?: string  // 更新时间
  submitted_at?: string // 兼容字段
  review_count: number
  reviews?: VerificationReview[]  // 审核历史记录
  dispute_status?: 'none' | 'open' | 'resolved'
  verification_expires_at?: string
  next_review_due_at?: string
  reverify_strategy?: string
}

export type ReviewQueueItem = {
  submission_id: string
  profile_id: number
  field_key: string
  declared_value: string
  status: string
  created_at?: string  // 提交时间
  updated_at?: string  // 更新时间
  submitted_at?: string // 兼容字段
  review_count?: number
  dispute_status?: string
  // 用户信息需要额外查询，暂不包含在submission中
}

export type ReviewQueueList = {
  submissions: ReviewQueueItem[]
  total?: number
  page?: number
  limit?: number
}

export type ReviewActionParams = {
  submissionId: string
  decision: 'approve' | 'reject' | 'request_resubmission'
  reviewNote?: string
  approvedValue?: string
  requestedDocuments?: string[]
  validityDays?: number
  nextReviewDays?: number
}

export type ReviewResult = {
  submission?: VerificationSubmissionDetail
  review_id?: string
}

const FIELD_KEY_MAP: Record<string, string> = {
  education: 'education',
  occupation: 'job',
  income: 'income',
}

function mapUiFieldToApiKey(fieldId: string): string {
  return FIELD_KEY_MAP[fieldId] || fieldId
}

export async function listFieldVerifications(profileId?: number): Promise<FieldVerificationSubmission[]> {
  const resolvedProfileId = profileId ?? getProfileId()
  if (!resolvedProfileId) return []

  const response = await gatewayJson<{ submissions?: FieldVerificationSubmission[] }>(
    `/v1/profile-verifications/submissions${queryString({
      profile_id: resolvedProfileId,
      limit: 20,
    })}`,
  )
  return response.submissions ?? []
}

export async function submitFieldVerification(params: {
  fieldId: string
  profileId?: number
  file?: File
  declaredValue?: string
}) {
  const profileId = params.profileId ?? getProfileId()
  const userId = getUserId()
  if (!profileId) throw new Error('缺少 profile_id')
  if (!userId) throw new Error('请先登录')

  let evidence: Record<string, unknown> | undefined
  if (params.file) {
    const base64 = await fileToBase64(params.file)
    evidence = {
      file_name: params.file.name,
      content_type: params.file.type || 'application/octet-stream',
      data_base64: base64,
    }
  }

  return gatewayJson<{ submission?: FieldVerificationSubmission }>(
    '/v1/profile-verifications/submissions',
    {
      method: 'POST',
      body: JSON.stringify({
        field_key: mapUiFieldToApiKey(params.fieldId),
        profile_id: profileId,
        subject_user_id: userId,
        declared_value: params.declaredValue,
        evidence,
        evidence_type: params.file ? 'document' : 'self_declared',
        evidence_channel: 'her-app',
      }),
    },
  )
}

async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

// ==================== 审核管理 API ====================

/**
 * 获取审核队列列表（管理员使用）
 */
export async function fetchReviewQueue(params?: {
  status?: string
  field_key?: string
  page?: number
  limit?: number
}): Promise<ReviewQueueList> {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.field_key) query.set('field_key', params.field_key)
  if (params?.page) query.set('page', params.page.toString())
  if (params?.limit) query.set('limit', params.limit.toString())

  const response = await gatewayJson<{ submissions?: ReviewQueueItem[]; total?: number; page?: number; limit?: number }>(
    `/v1/profile-verifications/submissions${query.toString() ? `?${query.toString()}` : ''}`,
    { includeAuth: true },
  )

  return {
    submissions: response.submissions || [],
    total: response.total,
    page: response.page,
    limit: response.limit,
  }
}

/**
 * 获取单个认证提交详情（管理员使用）
 */
export async function fetchVerificationDetail(submissionId: string): Promise<VerificationSubmissionDetail> {
  const response = await gatewayJson<{ submission: VerificationSubmissionDetail }>(
    `/v1/profile-verifications/submissions/${submissionId}`,
    { includeAuth: true },
  )
  // 从后端返回的 {submission: {...}} 结构中提取 submission 对象
  return response.submission
}

/**
 * 执行审核操作（管理员使用）
 */
export async function reviewFieldVerification(params: ReviewActionParams): Promise<ReviewResult> {
  return gatewayJson<ReviewResult>(
    `/v1/profile-verifications/submissions/${params.submissionId}/review`,
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        decision: params.decision,
        review_note: params.reviewNote,
        approved_value: params.approvedValue,
        requested_documents: params.requestedDocuments,
        validity_days: params.validityDays ?? 3650,
        next_review_days: params.nextReviewDays ?? 3650,
        reverify_strategy: 'on_change',
      }),
    },
  )
}

/**
 * 批量审核操作（管理员使用）
 */
export async function batchReviewFieldVerifications(params: {
  submissionIds: string[]
  decision: 'approve' | 'reject'
  reviewNote?: string
}): Promise<{ results: ReviewResult[]; success_count: number; failed_count: number }> {
  return gatewayJson<{ results: ReviewResult[]; success_count: number; failed_count: number }>(
    '/v1/profile-verifications/batch-review',
    {
      method: 'POST',
      includeAuth: true,
      body: JSON.stringify({
        submission_ids: params.submissionIds,
        decision: params.decision,
        review_note: params.reviewNote,
        validity_days: 3650,
        next_review_days: 3650,
        reverify_strategy: 'on_change',
      }),
    },
  )
}
