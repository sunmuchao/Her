import { describe, expect, test } from 'vitest'
import { buildGuideSteps, getGuidedRecordingState, getRecordingDurationSeconds } from '../../components/her/verification/verification-helpers'

describe('verification helpers', () => {
  const challenge = {
    required_actions: ['nod_up', 'turn_left', 'open_mouth'],
    spoken_code: '43',
  }

  test('按顺序构建引导步骤', () => {
    const steps = buildGuideSteps(challenge as never)

    expect(steps.map((step) => step.instruction)).toEqual([
      '请抬头',
      '请向左转头',
      '请张嘴',
      '请大声读出数字 43',
    ])
  })

  test('录制中只推进当前步骤和下一步骤', () => {
    const duration = getRecordingDurationSeconds(challenge as never)
    const start = getGuidedRecordingState({ challenge: challenge as never, recordingTime: 0, totalDurationSeconds: duration })
    const middle = getGuidedRecordingState({ challenge: challenge as never, recordingTime: 3, totalDurationSeconds: duration })
    const final = getGuidedRecordingState({ challenge: challenge as never, recordingTime: 9, totalDurationSeconds: duration })

    expect(start.currentStep?.instruction).toBe('请抬头')
    expect(start.nextStep?.instruction).toBe('请向左转头')

    expect(middle.currentStep?.instruction).toBe('请向左转头')
    expect(middle.nextStep?.instruction).toBe('请张嘴')

    expect(final.currentStep?.instruction).toBe('请大声读出数字 43')
    expect(final.nextStep).toBeNull()
  })

  test('根据动作和口令动态计算录制时长', () => {
    expect(getRecordingDurationSeconds(challenge as never)).toBe(10)
    expect(getRecordingDurationSeconds({ required_actions: ['nod_up'] } as never)).toBe(6)
  })
})
