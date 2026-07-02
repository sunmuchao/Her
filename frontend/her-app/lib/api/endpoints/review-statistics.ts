import { gatewayJson } from '@/lib/api/client'

export type ReviewStatistics = {
  total_reviews: number
  approve_count: number
  reject_count: number
  resubmission_count: number
  approve_rate: number
  reject_rate: number
  today_reviews: number
  today_approve: number
  today_reject: number
  average_review_time_minutes?: number
  pending_count: number
}

export type DailyReviewStatistics = {
  date: string
  total: number
  approve: number
  reject: number
  resubmission: number
}

/**
 * 获取审核统计数据（管理员使用）
 */
export async function fetchReviewStatistics(): Promise<ReviewStatistics> {
  return gatewayJson<ReviewStatistics>(
    '/v1/profile-verifications/statistics',
    { includeAuth: true },
  )
}

/**
 * 获取每日审核统计（管理员使用）
 */
export async function fetchDailyReviewStatistics(days?: number): Promise<DailyReviewStatistics[]> {
  const query = days ? `?days=${days}` : ''
  return gatewayJson<DailyReviewStatistics[]>(
    `/v1/profile-verifications/daily-statistics${query}`,
    { includeAuth: true },
  )
}