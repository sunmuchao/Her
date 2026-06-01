import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  answerAssessment,
  beginAssessment,
  fetchAssessmentInterpretation,
  getOrCreateAssessment,
  startAssessment,
} from '@/lib/api/endpoints/assessment'

describe('assessment endpoints', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts assessment start request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: async () =>
        JSON.stringify({
          card_type: 'assessment_intro',
          assessment_type: 'mbti_16',
          assessment_id: 'mbti_demo',
          intro_data: {
            title: 'MBTI 16型人格测评',
            description: '快速看清你的相处风格和关系偏好',
            duration: '约5分钟 · 20题',
            reward: '匹配质量提升10%',
          },
        }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const response = await startAssessment('42')

    expect(response.assessment_id).toBe('mbti_demo')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/gateway/v1/assessment/start',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    )
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
      user_key: '42',
      assessment_type: 'mbti_16',
    })
  })

  describe('getOrCreateAssessment - 断点续传', () => {
    it('returns resumed intro when user has incomplete assessment', async () => {
      // 测试：有未完成的测评，恢复进度
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        text: async () =>
          JSON.stringify({
            card_type: 'assessment_intro',
            assessment_id: 'mbti_existing',
            intro_data: {
              title: '继续上次的测评',
              description: '已答 5 题，还有 15 题',
              duration: '继续测评',
              reward: '上次退出时已保存进度，点击继续',
            },
            resumed: true,
            answered_count: 5,
          }),
      })
      vi.stubGlobal('fetch', fetchMock)

      const response = await getOrCreateAssessment('42')

      expect(response.assessment_id).toBe('mbti_existing')
      expect(response.resumed).toBe(true)
      expect(response.answered_count).toBe(5)
      expect(response.intro_data.title).toBe('继续上次的测评')
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/gateway/v1/assessment/get-or-create',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
        }),
      )
      expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
        user_key: '42',
        assessment_type: 'mbti_16',
      })
    })

    it('returns new intro when user has no incomplete assessment', async () => {
      // 测试：没有未完成的测评，创建新测评
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        text: async () =>
          JSON.stringify({
            card_type: 'assessment_intro',
            assessment_type: 'mbti_16',
            assessment_id: 'mbti_new',
            intro_data: {
              title: 'MBTI 恋爱测试',
              description: '测测你在恋爱中是哪一型',
              duration: '5分钟 · 20题',
              reward: '测完了解你的恋爱优势与雷区',
            },
          }),
      })
      vi.stubGlobal('fetch', fetchMock)

      const response = await getOrCreateAssessment('108')

      expect(response.assessment_id).toBe('mbti_new')
      expect(response.intro_data.title).toBe('MBTI 恋爱测试')
      // 没有 resumed 字段，说明是新测评
      expect(response.resumed).toBeUndefined()
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/gateway/v1/assessment/get-or-create',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
        }),
      )
      expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toMatchObject({
        user_key: '108',
        assessment_type: 'mbti_16',
      })
    })
  })

  it('posts answer and interpretation requests', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        text: async () =>
          JSON.stringify({
            card_type: 'assessment_question',
            assessment_id: 'mbti_demo',
            question_data: {
              current_question: 1,
              total_questions: 20,
              question_text: '题目',
              options: [],
              progress: 5,
              assessment_id: 'mbti_demo',
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () =>
          JSON.stringify({
            card_type: 'assessment_result',
            assessment_id: 'mbti_demo',
            result_data: {
              type_code: 'ENTJ',
              scores: {},
              dimension_rows: [],
              labels: [],
              interpretation_data: { summary: '总结', love_style: '风格', match_suggestions: ['建议'] },
              reward: 'ok',
              assessment_id: 'mbti_demo',
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () =>
          JSON.stringify({
            card_type: 'assessment_interpretation',
            assessment_id: 'mbti_demo',
            interpretation_data: { summary: '总结', love_style: '风格', match_suggestions: ['建议'] },
          }),
      })
    vi.stubGlobal('fetch', fetchMock)

    await beginAssessment('mbti_demo')
    await answerAssessment({ assessmentId: 'mbti_demo', questionIndex: 0, answer: 'A', userKey: '42' })
    await fetchAssessmentInterpretation({ assessmentId: 'mbti_demo', userKey: '42' })

    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({
      assessment_id: 'mbti_demo',
      question_index: 0,
      answer: 'A',
      user_key: '42',
    })
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({
      assessment_id: 'mbti_demo',
      user_key: '42',
    })
  })
})
