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

  it('renders chinese love language label from english dimension key', () => {
    const html = renderToStaticMarkup(
      React.createElement(AssessmentFeedbackCard, {
        data: {
          dimension: 'words_of_affirmation',
          score: 82,
          feedback_text: '你很在意语言上的确认和回应。',
        },
        assessmentType: 'love_language',
        onContinue: vi.fn(),
      }),
    )

    expect(html).toContain('肯定言词')
    expect(html).not.toContain('words_of_affirmation')
    expect(html).toContain('强倾向')
  })
})
