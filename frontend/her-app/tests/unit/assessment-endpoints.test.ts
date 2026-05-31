import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  answerAssessment,
  beginAssessment,
  fetchAssessmentInterpretation,
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
