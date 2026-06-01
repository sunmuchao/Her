import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AssessmentResultCard } from '@/components/assessment/AssessmentResultCard'

describe('AssessmentResultCard', () => {
  it('renders safely when dimension_rows is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AssessmentResultCard, {
        data: {
          type_code: 'INTJ',
          scores: {},
          labels: [],
          reward: 'ok',
          assessment_id: 'mbti_demo',
        },
      }),
    )

    expect(html).toContain('暂无雷达图数据')
    expect(html).toContain('INTJ')
  })

  it('renders safely when type_code is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AssessmentResultCard, {
        data: {
          scores: {},
          labels: [],
          reward: 'ok',
          assessment_id: 'love_demo',
        },
        assessmentType: 'love_language',
      }),
    )

    expect(html).toContain('暂无雷达图数据')
    expect(html).toContain('--')
  })
})
