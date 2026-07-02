'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchReviewQueue,
  fetchVerificationDetail,
  reviewFieldVerification,
  batchReviewFieldVerifications,
  type ReviewQueueParams,
  type ReviewActionParams,
  type VerificationSubmissionDetail,
} from '@/lib/api/endpoints/field-verification'
import {
  fetchVideoReviewQueue,
  fetchReportReviewQueue,
  fetchPhotoRiskQueue,
  fetchAppealReviewQueue,
  reviewVideoVerification,
  reviewReportCase,
  reviewPhotoRisk,
  reviewAppealCase,
  type VideoReviewParams,
  type ReportReviewParams,
  type PhotoRiskReviewParams,
  type AppealReviewParams,
} from '@/lib/api/endpoints/all-review-types'
import { queryKeys } from '@/lib/query-keys'
import type { GatewayRequestInit } from '@/lib/api/client'

/**
 * 字段认证审核队列 React Query Hook
 *
 * @param params - 查询参数（status, field_key, limit等）
 * @returns React Query 结果对象
 */
export function useFieldReviewQueue(params: ReviewQueueParams) {
  return useQuery({
    queryKey: queryKeys.reviewQueue(params),
    queryFn: ({ signal }) =>
      fetchReviewQueue({
        ...params,
        signal: signal as AbortSignal,
      } as ReviewQueueParams & { signal: AbortSignal }),
    staleTime: 60 * 1000, // 1分钟内数据视为新鲜
    gcTime: 5 * 60 * 1000, // 缓存保留5分钟
    enabled: !!params.field_key, // 仅在有 field_key 时启用
  })
}

/**
 * 审核详情 React Query Hook
 *
 * @param submissionId - 提交ID
 * @returns React Query 结果对象
 */
export function useVerificationDetail(submissionId: string) {
  return useQuery({
    queryKey: ['verification', 'detail', submissionId],
    queryFn: ({ signal }) =>
      fetchVerificationDetail(submissionId),
    staleTime: 5 * 60 * 1000, // 5分钟内数据视为新鲜
    enabled: !!submissionId, // 仅在有 submissionId 时启用
  })
}

/**
 * 字段认证审核操作 Mutation Hook
 *
 * 审核成功后自动刷新队列
 */
export function useFieldReviewMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: ReviewActionParams) => reviewFieldVerification(params),
    onSuccess: () => {
      // 审核成功后刷新所有审核队列
      queryClient.invalidateQueries({ queryKey: ['review', 'queue'] })
      queryClient.invalidateQueries({ queryKey: ['verification', 'submissions'] })
    },
  })
}

/**
 * 批量审核操作 Mutation Hook
 */
export function useBatchReviewMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: { submissionIds: string[]; decision: 'approve' | 'reject'; reviewNote?: string }) =>
      batchReviewFieldVerifications(params),
    onSuccess: () => {
      // 批量审核成功后刷新队列
      queryClient.invalidateQueries({ queryKey: ['review', 'queue'] })
    },
  })
}

/**
 * 活体视频审核队列 React Query Hook
 */
export function useVideoReviewQueue() {
  return useQuery({
    queryKey: queryKeys.videoReviewQueue,
    queryFn: ({ signal }) =>
      fetchVideoReviewQueue(),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}

/**
 * 活体视频审核操作 Mutation Hook
 */
export function useVideoReviewMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: VideoReviewParams) => reviewVideoVerification(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.videoReviewQueue })
    },
  })
}

/**
 * 举报审核队列 React Query Hook
 */
export function useReportReviewQueue() {
  return useQuery({
    queryKey: queryKeys.reportReviewQueue,
    queryFn: ({ signal }) =>
      fetchReportReviewQueue(),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}

/**
 * 举报审核操作 Mutation Hook
 */
export function useReportReviewMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: ReportReviewParams) => reviewReportCase(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.reportReviewQueue })
    },
  })
}

/**
 * 照片风险审核队列 React Query Hook
 */
export function usePhotoReviewQueue() {
  return useQuery({
    queryKey: queryKeys.photoReviewQueue,
    queryFn: ({ signal }) =>
      fetchPhotoRiskQueue(),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}

/**
 * 照片风险审核操作 Mutation Hook
 */
export function usePhotoReviewMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: PhotoRiskReviewParams) => reviewPhotoRisk(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.photoReviewQueue })
    },
  })
}

/**
 * 申诉审核队列 React Query Hook
 */
export function useAppealReviewQueue() {
  return useQuery({
    queryKey: queryKeys.appealReviewQueue,
    queryFn: ({ signal }) =>
      fetchAppealReviewQueue(),
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
  })
}

/**
 * 申诉审核操作 Mutation Hook
 */
export function useAppealReviewMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (params: AppealReviewParams) => reviewAppealCase(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.appealReviewQueue })
    },
  })
}