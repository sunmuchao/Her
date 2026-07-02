'use client'

import { useCallback, useState } from 'react'
import {
  fetchReviewQueue,
  fetchVerificationDetail,
  reviewFieldVerification,
  batchReviewFieldVerifications,
  type ReviewQueueList,
  type VerificationSubmissionDetail,
  type ReviewActionParams,
} from '@/lib/api/endpoints/field-verification'
import { notifyVerificationResult } from '@/lib/utils/verification-notification'
import { getErrorMessage } from '@/lib/api/errors'

export function useVerificationReview() {
  const [queue, setQueue] = useState<ReviewQueueList | null>(null)
  const [selectedItem, setSelectedItem] = useState<VerificationSubmissionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitMessage, setSubmitMessage] = useState<string | null>(null)

  /**
   * 加载审核队列
   */
  const loadQueue = useCallback(async (status?: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchReviewQueue({
        status: status || 'submitted,under_review',
        field_key: 'education',
        limit: 20,
      })
      setQueue(data)
    } catch (err) {
      setError(getErrorMessage(err))
      setQueue(null)
    } finally {
      setLoading(false)
    }
  }, [])

  /**
   * 加载单个提交详情
   */
  const loadDetail = useCallback(async (submissionId: string) => {
    try {
      const detail = await fetchVerificationDetail(submissionId)
      setSelectedItem(detail)
    } catch (err) {
      setSubmitMessage(getErrorMessage(err, '加载详情失败'))
    }
  }, [])

  /**
   * 执行审核操作
   */
  const handleReview = useCallback(
    async (params: ReviewActionParams) => {
      setIsSubmitting(true)
      setSubmitMessage(null)
      try {
        const result = await reviewFieldVerification(params)
        setSubmitMessage('审核完成')

        // 发送审核结果通知给用户
        if (result.submission) {
          await notifyVerificationResult({
            userId: result.submission.user_id,
            profileId: result.submission.profile_id,
            submissionId: result.submission.submission_id,
            decision: params.decision,
            approvedValue: params.approvedValue,
            requestedDocuments: params.requestedDocuments,
            reviewNote: params.reviewNote,
          })
        }

        setSelectedItem(null)
        await loadQueue() // 刷新队列
      } catch (err) {
        setSubmitMessage(getErrorMessage(err, '审核操作失败'))
      } finally {
        setIsSubmitting(false)
      }
    },
    [loadQueue],
  )

  /**
   * 执行批量审核操作
   */
  const handleBatchReview = useCallback(
    async (submissionIds: string[], decision: 'approve' | 'reject', reviewNote?: string) => {
      setIsSubmitting(true)
      setSubmitMessage(null)
      try {
        const result = await batchReviewFieldVerifications({
          submissionIds,
          decision,
          reviewNote,
        })
        setSubmitMessage(`批量审核完成：成功 ${result.success_count} 条，失败 ${result.failed_count} 条`)
        await loadQueue() // 刷新队列
      } catch (err) {
        setSubmitMessage(getErrorMessage(err, '批量审核操作失败'))
      } finally {
        setIsSubmitting(false)
      }
    },
    [loadQueue],
  )

  /**
   * 清除选中项
   */
  const clearSelection = useCallback(() => {
    setSelectedItem(null)
    setSubmitMessage(null)
  }, [])

  /**
   * 清除消息
   */
  const clearMessage = useCallback(() => {
    setSubmitMessage(null)
  }, [])

  return {
    queue,
    selectedItem,
    loading,
    error,
    isSubmitting,
    submitMessage,
    loadQueue,
    loadDetail,
    handleReview,
    handleBatchReview,
    clearSelection,
    clearMessage,
  }
}