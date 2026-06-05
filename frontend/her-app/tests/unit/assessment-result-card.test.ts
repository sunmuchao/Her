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
          interpretation_data: {
            summary: '不应在结果卡展示的大段说明',
            love_style: '也不应在这里展示',
            match_suggestions: ['同样不应显示'],
          },
          labels: [],
          reward: 'ok',
          assessment_id: 'mbti_demo',
        },
      }),
    )

    expect(html).toContain('暂无雷达图数据')
    expect(html).toContain('INTJ')
    expect(html).not.toContain('不应在结果卡展示的大段说明')
  })

  it('renders compact attachment quadrant result and defers long explanation to xiaoya', () => {
    const html = renderToStaticMarkup(
      React.createElement(AssessmentResultCard, {
        data: {
          type_code: 'anxious',
          scores: { anxiety: 78, avoidance: 29 },
          dimension_rows: [
            { key: 'anxiety', name: '关系不安度', score: 78, level: 'high', trait: '回应敏感' },
            { key: 'avoidance', name: '亲密后撤度', score: 29, level: 'low', trait: '靠近自如' },
          ],
          quadrant: {
            x_key: 'avoidance',
            x_name: '亲密后撤度',
            x_score: 29,
            y_key: 'anxiety',
            y_name: '关系不安度',
            y_score: 78,
            type_code: 'anxious',
            type_name: '高敏确认型',
            quadrants: {
              top_left: { type_code: 'anxious', label: '高敏确认型' },
              top_right: { type_code: 'fearful', label: '拉扯矛盾型' },
              bottom_left: { type_code: 'secure', label: '稳定靠近型' },
              bottom_right: { type_code: 'avoidant', label: '边界后撤型' },
            },
          },
          interpretation_data: {
            summary: '你对关系变化比较敏感，但不太会主动后退。',
            relationship_drive: '你很在意对方有没有持续回应你。',
            triggers: '忽冷忽热最容易触发你。',
            stabilizers: '清楚表达会让你更稳。',
            common_misread: '你容易把忙理解成不在乎。',
            communication_advice: '先别脑补，把不安说出口。',
            card_tip: '少一点猜测，多一点确认。',
          },
          labels: ['高敏确认型', '回应敏感', '靠近自如'],
          reward: 'ok',
          assessment_id: 'attachment_demo',
        },
        assessmentType: 'attachment_style',
      }),
    )

    expect(html).toContain('ECR 坐标')
    expect(html).toContain('高敏确认型')
    expect(html).not.toContain('这次的相处坐标')
    expect(html).not.toContain('一句提醒')
    expect(html).not.toContain('详细解释看小雅')
    expect(html).not.toContain('你的关系驱动力')
    expect(html).not.toContain('最容易触发你的时刻')
    expect(html).not.toContain('暂无坐标图数据')
  })
})
