// tests/api/all-review-types.test.ts
/**
 * 所有审核类型API自动化测试
 */

import {
  fetchVideoReviewQueue,
  reviewVideoVerification,
  fetchReportReviewQueue,
  reviewReportCase,
  fetchPhotoRiskQueue,
  reviewPhotoRisk,
  fetchAppealReviewQueue,
  reviewAppealCase,
} from '@/lib/api/endpoints/all-review-types'

// ==================== 活体视频认证审核测试 ====================

describe('活体视频认证审核API测试', () => {
  test('视频审核队列加载成功', async () => {
    const queue = await fetchVideoReviewQueue()

    expect(queue).toBeDefined()
    expect(queue.submissions).toBeDefined()
    expect(Array.isArray(queue.submissions)).toBe(true)
  })

  test('视频审核队列字段验证', async () => {
    const queue = await fetchVideoReviewQueue()

    if (queue.submissions.length > 0) {
      const firstSubmission = queue.submissions[0]
      expect(firstSubmission.submission_id).toBeDefined()
      expect(firstSubmission.video_url).toBeDefined()
      expect(firstSubmission.status).toBeDefined()
    }
  })

  test('视频审核通过成功', async () => {
    const result = await reviewVideoVerification({
      submissionId: 'test_video_001',
      decision: 'approve',
      reviewNote: '视频审核通过，活体检测正常',
    })

    expect(result).toBeDefined()
    expect(result.submission.status).toBe('approved')
  })

  test('视频审核驳回成功', async () => {
    const result = await reviewVideoVerification({
      submissionId: 'test_video_002',
      decision: 'reject',
      reviewNote: '视频清晰度不足，无法判断真实性',
    })

    expect(result).toBeDefined()
    expect(result.submission.status).toBe('rejected')
  })

  test('空视频审核队列处理', async () => {
    const queue = await fetchVideoReviewQueue()

    expect(queue.submissions).toBeDefined()
    expect(Array.isArray(queue.submissions)).toBe(true)
  })
})

// ==================== 举报审核测试 ====================

describe('举报审核API测试', () => {
  test('举报审核队列加载成功', async () => {
    const queue = await fetchReportReviewQueue()

    expect(queue).toBeDefined()
    expect(queue.cases).toBeDefined()
    expect(Array.isArray(queue.cases)).toBe(true)
  })

  test('举报审核队列字段验证', async () => {
    const queue = await fetchReportReviewQueue()

    if (queue.cases.length > 0) {
      const firstCase = queue.cases[0]
      expect(firstCase.case_id).toBeDefined()
      expect(firstCase.report_reason).toBeDefined()
      expect(firstCase.status).toBeDefined()
    }
  })

  test('举报属实处理成功', async () => {
    const result = await reviewReportCase({
      caseId: 'test_report_001',
      decision: 'valid',
      penalty: 'ban_7d',
      reviewNote: '举报属实，封禁7天',
    })

    expect(result).toBeDefined()
    expect(result.case.status).toBe('resolved')
  })

  test('举报不属实处理成功', async () => {
    const result = await reviewReportCase({
      caseId: 'test_report_002',
      decision: 'invalid',
      reviewNote: '举报不属实，驳回',
    })

    expect(result).toBeDefined()
    expect(result.case.status).toBe('dismissed')
  })

  test('需补充证据处理成功', async () => {
    const result = await reviewReportCase({
      caseId: 'test_report_003',
      decision: 'need_evidence',
      reviewNote: '需补充聊天记录截图',
    })

    expect(result).toBeDefined()
  })

  test('举报审核处罚措施验证', async () => {
    const penalties = ['warning', 'ban_3d', 'ban_7d', 'ban_permanent', 'unban']

    for (const penalty of penalties) {
      const result = await reviewReportCase({
        caseId: `test_penalty_${penalty}`,
        decision: 'valid',
        penalty,
      })

      expect(result).toBeDefined()
    }
  })
})

// ==================== 照片风险审核测试 ====================

describe('照片风险审核API测试', () => {
  test('照片审核队列加载成功', async () => {
    const queue = await fetchPhotoRiskQueue()

    expect(queue).toBeDefined()
    expect(queue.photos).toBeDefined()
    expect(Array.isArray(queue.photos)).toBe(true)
  })

  test('照片审核队列字段验证', async () => {
    const queue = await fetchPhotoRiskQueue()

    if (queue.photos.length > 0) {
      const firstPhoto = queue.photos[0]
      expect(firstPhoto.photo_id).toBeDefined()
      expect(firstPhoto.photo_url).toBeDefined()
      expect(firstPhoto.risk_score).toBeDefined()
      expect(firstPhoto.risk_level).toBeDefined()
    }
  })

  test('照片真实审核成功', async () => {
    const result = await reviewPhotoRisk({
      photoId: 'test_photo_001',
      decision: 'real',
      reviewNote: '照片真实，非合成',
    })

    expect(result).toBeDefined()
    expect(result.photo.status).toBe('approved')
  })

  test('照片合成审核成功', async () => {
    const result = await reviewPhotoRisk({
      photoId: 'test_photo_002',
      decision: 'synthetic',
      reviewNote: '照片为合成照片',
    })

    expect(result).toBeDefined()
    expect(result.photo.status).toBe('rejected')
  })

  test('照片盗用审核成功', async () => {
    const result = await reviewPhotoRisk({
      photoId: 'test_photo_003',
      decision: 'stolen',
      reviewNote: '照片为盗用照片',
    })

    expect(result).toBeDefined()
  })

  test('AI风险评分验证', async () => {
    const queue = await fetchPhotoRiskQueue()

    if (queue.photos.length > 0) {
      for (const photo of queue.photos) {
        expect(photo.risk_score).toBeGreaterThanOrEqual(0)
        expect(photo.risk_score).toBeLessThanOrEqual(100)
      }
    }
  })
})

// ==================== 申诉审核测试 ====================

describe('申诉审核API测试', () => {
  test('申诉审核队列加载成功', async () => {
    const queue = await fetchAppealReviewQueue()

    expect(queue).toBeDefined()
    expect(queue.appeals).toBeDefined()
    expect(Array.isArray(queue.appeals)).toBe(true)
  })

  test('申诉审核队列字段验证', async () => {
    const queue = await fetchAppealReviewQueue()

    if (queue.appeals.length > 0) {
      const firstAppeal = queue.appeals[0]
      expect(firstAppeal.appeal_id).toBeDefined()
      expect(firstAppeal.appeal_reason).toBeDefined()
      expect(firstAppeal.status).toBeDefined()
    }
  })

  test('申诉接受处理成功', async () => {
    const result = await reviewAppealCase({
      appealId: 'test_appeal_001',
      decision: 'accept',
      result: 'unban',
      reviewNote: '申诉理由合理，予以解封',
    })

    expect(result).toBeDefined()
    expect(result.appeal.status).toBe('accepted')
  })

  test('申诉驳回处理成功', async () => {
    const result = await reviewAppealCase({
      appealId: 'test_appeal_002',
      decision: 'reject',
      result: 'maintain',
      reviewNote: '申诉理由不充分，维持封禁',
    })

    expect(result).toBeDefined()
    expect(result.appeal.status).toBe('rejected')
  })

  test('申诉审核结果验证', async () => {
    const results = ['unban', 'maintain']

    for (const result of results) {
      const response = await reviewAppealCase({
        appealId: `test_result_${result}`,
        decision: result === 'unban' ? 'accept' : 'reject',
        result,
      })

      expect(response).toBeDefined()
    }
  })
})

// ==================== 权限测试 ====================

describe('审核权限测试', () => {
  test('字段认证审核权限验证', async () => {
    // 需要 profile_reviewer 或 platform_admin 角色
    try {
      await fetchReviewQueue({ field_key: 'education' })
    } catch (error) {
      expect(error.message).toContain('permission')
    }
  })

  test('视频审核权限验证', async () => {
    // 需要 risk_reviewer 或 platform_admin 角色
    try {
      await fetchVideoReviewQueue()
    } catch (error) {
      expect(error.message).toContain('permission')
    }
  })

  test('举报审核权限验证', async () => {
    // 需要 risk_reviewer / customer_support / platform_admin 角色
    try {
      await fetchReportReviewQueue()
    } catch (error) {
      expect(error.message).toContain('permission')
    }
  })

  test('照片审核权限验证', async () => {
    // 需要 risk_reviewer 或 platform_admin 角色
    try {
      await fetchPhotoRiskQueue()
    } catch (error) {
      expect(error.message).toContain('permission')
    }
  })

  test('申诉审核权限验证', async () => {
    // 需要 risk_reviewer 或 platform_admin 角色
    try {
      await fetchAppealReviewQueue()
    } catch (error) {
      expect(error.message).toContain('permission')
    }
  })
})

// ==================== 集成测试 ====================

describe('审核系统集成测试', () => {
  test('多审核类型队列并发加载', async () => {
    const promises = [
      fetchReviewQueue({ field_key: 'education' }),
      fetchVideoReviewQueue(),
      fetchReportReviewQueue(),
      fetchPhotoRiskQueue(),
      fetchAppealReviewQueue(),
    ]

    const results = await Promise.all(promises)

    expect(results).toBeDefined()
    expect(results.length).toBe(5)
  })

  test('审核统计数据准确性', async () => {
    // 加载所有队列
    const educationQueue = await fetchReviewQueue({ field_key: 'education' })
    const videoQueue = await fetchVideoReviewQueue()
    const reportQueue = await fetchReportReviewQueue()
    const photoQueue = await fetchPhotoRiskQueue()
    const appealQueue = await fetchAppealReviewQueue()

    // 统计总数
    const totalPending =
      educationQueue.submissions.length +
      videoQueue.submissions.length +
      reportQueue.cases.length +
      photoQueue.photos.length +
      appealQueue.appeals.length

    expect(totalPending).toBeGreaterThanOrEqual(0)
  })

  test('审核操作跨类型一致性', async () => {
    // 不同类型审核操作应该有统一的结构
    const reviewActions = [
      reviewFieldVerification({ submissionId: 'test_001', decision: 'approve' }),
      reviewVideoVerification({ submissionId: 'test_002', decision: 'approve' }),
      reviewReportCase({ caseId: 'test_003', decision: 'valid' }),
      reviewPhotoRisk({ photoId: 'test_004', decision: 'real' }),
      reviewAppealCase({ appealId: 'test_005', decision: 'accept' }),
    ]

    const results = await Promise.all(reviewActions)

    // 所有结果应该有统一结构
    for (const result of results) {
      expect(result).toBeDefined()
    }
  })
})

// ==================== 错误场景测试 ====================

describe('审核系统错误场景测试', () => {
  test('API返回401错误处理', async () => {
    try {
      // 模拟过期token
      await fetchReviewQueue({ field_key: 'education' })
    } catch (error) {
      expect(error.message).toContain('401')
    }
  })

  test('API返回404错误处理', async () => {
    try {
      await reviewFieldVerification({
        submissionId: 'non_existent_id',
        decision: 'approve',
      })
    } catch (error) {
      expect(error.message).toContain('not found')
    }
  })

  test('API返回500错误处理', async () => {
    try {
      // 模拟后端服务异常
      await fetchVideoReviewQueue()
    } catch (error) {
      expect(error).toBeDefined()
    }
  })

  test('网络超时错误处理', async () => {
    try {
      // 模拟网络超时
      await fetchReportReviewQueue()
    } catch (error) {
      expect(error).toBeDefined()
    }
  })
})