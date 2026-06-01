import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { AssessmentFeedbackCard } from '@/components/assessment/AssessmentFeedbackCard'

describe('AssessmentFeedbackCard', () => {
  it('renders safely when dimension is missing', () => {
    const html = renderToStaticMarkup(
      React.createElement(AssessmentFeedbackCard, {
        data: {
          dimension_name: '肯定言词',
          feedback_text: '你会更在意被明确表达爱意。',
        },
        assessmentType: 'love_language',
        onContinue: vi.fn(),
      }),
    )

    expect(html).toContain('肯定言词')
    expect(html).toContain('你会更在意被明确表达爱意。')
    expect(html).toContain('0')
  })
})
