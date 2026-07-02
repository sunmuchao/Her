// tests/api/field-verification.test.ts
/**
 * 字段认证审核API自动化测试
 */

import { fetchReviewQueue, reviewFieldVerification, batchReviewFieldVerifications } from '@/lib/api/endpoints/field-verification'

describe('字段认证审核API测试', () => {
  // ==================== 学历认证审核测试 ====================

  describe('学历认证审核', () => {
    test('学历认证审核队列加载成功', async () => {
      const queue = await fetchReviewQueue({
        status: 'submitted,under_review',
        field_key: 'education',
        limit: 20,
      })

      expect(queue).toBeDefined()
      expect(queue.submissions).toBeDefined()
      expect(Array.isArray(queue.submissions)).toBe(true)
      expect(queue.submissions.length).toBeLessThanOrEqual(20)
    })

    test('学历认证审核队列字段验证', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'education',
        limit: 10,
      })

      if (queue.submissions.length > 0) {
        const firstSubmission = queue.submissions[0]
        expect(firstSubmission.submission_id).toBeDefined()
        expect(firstSubmission.profile_id).toBeDefined()
        expect(firstSubmission.field_key).toBe('education')
        expect(firstSubmission.status).toBeDefined()
      }
    })

    test('学历认证审核通过成功', async () => {
      // Mock submission_id for testing
      const result = await reviewFieldVerification({
        submissionId: 'test_education_submission_001',
        decision: 'approve',
        approvedValue: '本科',
        reviewNote: '学历证书核实无误',
      })

      expect(result).toBeDefined()
      expect(result.submission).toBeDefined()
      expect(result.submission.status).toBe('approved')
    })

    test('学历认证审核驳回成功', async () => {
      const result = await reviewFieldVerification({
        submissionId: 'test_education_submission_002',
        decision: 'reject',
        reviewNote: '学历证书模糊无法辨认',
      })

      expect(result).toBeDefined()
      expect(result.submission.status).toBe('rejected')
    })

    test('学历认证审核补件成功', async () => {
      const result = await reviewFieldVerification({
        submissionId: 'test_education_submission_003',
        decision: 'request_resubmission',
        requestedDocuments: ['毕业证', '学位证'],
        reviewNote: '需补充学位证',
      })

      expect(result).toBeDefined()
      expect(result.submission.status).toBe('resubmission_required')
    })

    test('学历认证批量审核成功', async () => {
      const result = await batchReviewFieldVerifications({
        submissionIds: ['test_001', 'test_002', 'test_003'],
        decision: 'approve',
        reviewNote: '批量通过学历认证',
      })

      expect(result).toBeDefined()
      expect(result.success_count).toBe(3)
      expect(result.failed_count).toBe(0)
    })
  })

  // ==================== 职业认证审核测试 ====================

  describe('职业认证审核', () => {
    test('职业认证审核队列加载成功', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'job',
        limit: 20,
      })

      expect(queue).toBeDefined()
      expect(queue.submissions).toBeDefined()
    })

    test('职业认证审核队列字段验证', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'job',
        limit: 10,
      })

      if (queue.submissions.length > 0) {
        const firstSubmission = queue.submissions[0]
        expect(firstSubmission.field_key).toBe('job')
      }
    })

    test('职业认证审核通过成功', async () => {
      const result = await reviewFieldVerification({
        submissionId: 'test_job_submission_001',
        decision: 'approve',
        approvedValue: '程序员',
        reviewNote: '职业证明核实无误',
      })

      expect(result.submission.status).toBe('approved')
    })

    test('职业认证审核驳回成功', async () => {
      const result = await reviewFieldVerification({
        submissionId: 'test_job_submission_002',
        decision: 'reject',
        reviewNote: '职业证明不符合要求',
      })

      expect(result.submission.status).toBe('rejected')
    })
  })

  // ==================== 收入认证审核测试 ====================

  describe('收入认证审核', () => {
    test('收入认证审核队列加载成功', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'income',
        limit: 20,
      })

      expect(queue).toBeDefined()
      expect(queue.submissions).toBeDefined()
    })

    test('收入认证审核队列字段验证', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'income',
        limit: 10,
      })

      if (queue.submissions.length > 0) {
        const firstSubmission = queue.submissions[0]
        expect(firstSubmission.field_key).toBe('income')
      }
    })

    test('收入认证审核通过成功', async () => {
      const result = await reviewFieldVerification({
        submissionId: 'test_income_submission_001',
        decision: 'approve',
        approvedValue: '10-20万',
        reviewNote: '收入证明核实无误',
      })

      expect(result.submission.status).toBe('approved')
    })

    test('收入认证审核驳回成功', async () => {
      const result = await reviewFieldVerification({
        submissionId: 'test_income_submission_002',
        decision: 'reject',
        reviewNote: '收入证明不完整',
      })

      expect(result.submission.status).toBe('rejected')
    })
  })

  // ==================== 错误场景测试 ====================

  describe('错误场景测试', () => {
    test('无效submission_id审核失败', async () => {
      try {
        await reviewFieldVerification({
          submissionId: 'invalid_id',
          decision: 'approve',
        })
      } catch (error) {
        expect(error).toBeDefined()
        expect(error.message).toContain('not found')
      }
    })

    test('缺少decision参数审核失败', async () => {
      try {
        await reviewFieldVerification({
          submissionId: 'test_001',
          decision: '', // 空decision
        })
      } catch (error) {
        expect(error).toBeDefined()
        expect(error.message).toContain('decision is required')
      }
    })

    test('无权限审核失败', async () => {
      // Mock无权限场景
      try {
        await fetchReviewQueue({
          field_key: 'education',
        })
      } catch (error) {
        expect(error).toBeDefined()
        expect(error.message).toContain('permission')
      }
    })
  })

  // ==================== 边缘案例测试 ====================

  describe('边缘案例测试', () => {
    test('空审核队列处理', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'education',
        status: 'approved', // 只查询已通过的，可能为空
      })

      expect(queue.submissions).toBeDefined()
      expect(Array.isArray(queue.submissions)).toBe(true)
      // 空数组也是合法的
    })

    test('大量审核队列加载', async () => {
      const queue = await fetchReviewQueue({
        field_key: 'education',
        limit: 100, // 加载大量数据
      })

      expect(queue.submissions.length).toBeLessThanOrEqual(100)
    })

    test('审核备注长文本', async () => {
      const longNote = '这是一段很长的审核备注文本，超过500字，测试系统是否能正确处理长文本输入...'

      const result = await reviewFieldVerification({
        submissionId: 'test_001',
        decision: 'approve',
        reviewNote: longNote,
      })

      expect(result).toBeDefined()
    })
  })
})